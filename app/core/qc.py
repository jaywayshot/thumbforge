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


def validate_text(headline: Optional[str], sub_text: Optional[str], platform: str) -> tuple[list[str], list[str]]:
    """플랫폼 금지문구/주의문구 검사"""
    text_blob = " ".join(t for t in (headline, sub_text) if t)
    forbidden = check_forbidden_words(text_blob, platform)
    warnings = check_warning_words(text_blob, platform)
    return forbidden, warnings
