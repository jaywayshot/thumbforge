"""
검수 / CTR 점수 계산 - 시선 집중 / 대비 / 색감 다양성 / 텍스트 영역 비율 종합
"""
from __future__ import annotations
from typing import Optional

import numpy as np
from PIL import Image

from app.services.concept_loader import (
    check_forbidden_words,
    check_warning_words,
    get_platform,
)


def _saliency_score(image: Image.Image) -> int:
    """
    매우 단순화된 시선 집중도 휴리스틱.
    - 중앙 영역과 외곽 영역의 대비/밝기 차이가 클수록 시선 집중↑
    - 실제 SaaS에서는 OpenCV saliency나 학습 모델로 교체
    """
    gray = np.array(image.convert("L"), dtype=np.float32)
    h, w = gray.shape
    cy, cx = h // 2, w // 2
    rh, rw = h // 4, w // 4
    center = gray[cy - rh:cy + rh, cx - rw:cx + rw]
    # 외곽: 가장자리 띠
    edge = np.concatenate([
        gray[:rh, :].ravel(),
        gray[-rh:, :].ravel(),
        gray[:, :rw].ravel(),
        gray[:, -rw:].ravel(),
    ])
    center_std = float(center.std())
    diff = abs(float(center.mean()) - float(edge.mean()))
    score = int(min(100, center_std * 0.8 + diff * 1.5))
    return max(0, score)


def _color_diversity_score(image: Image.Image) -> int:
    """색 다양성: 색이 너무 많으면 잡스럽고, 너무 적으면 단조"""
    small = image.convert("RGB").resize((64, 64))
    arr = np.array(small).reshape(-1, 3)
    # 양자화
    quant = (arr // 32).astype(np.int32)
    unique = len(np.unique(quant.view([('', quant.dtype)] * 3)))
    # 30~120 사이가 sweet spot
    if 30 <= unique <= 120:
        return 100
    if unique < 30:
        return int(unique / 30 * 80)
    return max(50, 100 - (unique - 120) // 4)


def estimate_ctr_score(
    image: Image.Image,
    qc_report: dict,
    has_discount: bool = False,
    has_badge: bool = False,
) -> int:
    """
    종합 CTR 점수 (휴리스틱).
    실제 서비스에서는 학습된 모델로 교체.
    """
    gray = np.array(image.convert("L"))
    contrast = float(gray.std())
    brightness = float(gray.mean())

    score = 40
    # 1) 대비 (시선 집중)
    score += min(20, int(contrast / 4))
    # 2) 적정 밝기
    if 70 <= brightness <= 210:
        score += 10
    # 3) 시선 집중도
    sal = _saliency_score(image)
    score += sal // 8       # 최대 +12
    # 4) 색 다양성
    div = _color_diversity_score(image)
    score += div // 14      # 최대 +7
    # 5) 할인/뱃지 (클릭 유도)
    if has_discount:
        score += 8
    if has_badge:
        score += 5
    # 6) QC 페널티
    if not qc_report.get("passed", True):
        score -= 12
    score += int(qc_report.get("text_legibility", 80) / 25)

    return max(0, min(100, score))


def qc_scene_check(image: Image.Image, product_info: Optional[object] = None) -> list[str]:
    """
    라이프스타일 신 자체 검수(휴리스틱). 문제 발견 시 issue 문자열 리스트 반환(없으면 빈 리스트).
    - 생성 실패(거의 균일/저대비) 검출 → 제품이 배경에 묻히거나 빈 이미지
    - 색 다양성 극단 검출 (단색 배경 = 생성 실패 가능성)
    실제 객체 인식(사람/마네킹)은 negative prompt 로 1차 차단하고, 여기선
    합성 결과의 가독성/품질 위주로 본다.
    """
    issues: list[str] = []
    gray = np.array(image.convert("L"), dtype=np.float32)
    contrast = float(gray.std())
    if contrast < 12:
        issues.append("전체 대비가 너무 낮음 (제품이 배경에 묻혔거나 생성 실패 가능)")

    # 색 다양성: 거의 단색이면 배경 생성 실패 의심
    small = np.array(image.convert("RGB").resize((48, 48))).reshape(-1, 3)
    quant = (small // 32).astype(np.int32)
    unique = len(np.unique(quant.view([('', quant.dtype)] * 3)))
    if unique < 4:
        issues.append("색 다양성이 비정상적으로 낮음 (배경 생성 실패 의심)")

    # 거의 흰/검 한 색으로 꽉 찬 경우
    mean = float(gray.mean())
    if mean > 250 or mean < 6:
        issues.append("이미지가 거의 단일 색 (생성 실패 의심)")

    return issues


def validate_text(headline: Optional[str], sub_text: Optional[str], platform: str) -> tuple[list[str], list[str]]:
    """플랫폼 금지문구/주의문구 검사"""
    text_blob = " ".join(t for t in (headline, sub_text) if t)
    forbidden = check_forbidden_words(text_blob, platform)
    warnings = check_warning_words(text_blob, platform)
    return forbidden, warnings
