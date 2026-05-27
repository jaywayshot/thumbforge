"""
Mock Provider - API 키 없이 동작
── 그라데이션 / 대각선 분할 / 솔리드 + 노이즈/조명효과로
   '실제 스튜디오 배경' 같은 느낌을 로컬에서 합성
── 인터넷/API 불필요 → 즉시 테스트 가능
"""
from __future__ import annotations

import math
import random
from functools import lru_cache
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from app.providers.base import BackgroundProvider, TextSuggestionProvider, QCProvider


# ───────── 유틸 ─────────

def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _make_gradient(width: int, height: int, colors: list[str], angle_deg: float = 135) -> Image.Image:
    """N-stop 선형 그라데이션"""
    if len(colors) < 2:
        colors = colors + colors
    rgb_stops = [_hex_to_rgb(c) for c in colors]
    n = len(rgb_stops)

    # 방향 벡터
    rad = math.radians(angle_deg)
    dx, dy = math.cos(rad), math.sin(rad)

    # 좌표 격자
    xs = np.arange(width, dtype=np.float32)[None, :]
    ys = np.arange(height, dtype=np.float32)[:, None]
    proj = xs * dx + ys * dy

    # 0~1 정규화
    proj -= proj.min()
    proj /= max(proj.max(), 1e-6)

    # 각 stop 위치
    positions = np.linspace(0, 1, n)
    out = np.zeros((height, width, 3), dtype=np.float32)
    for ch in range(3):
        values = np.array([c[ch] for c in rgb_stops], dtype=np.float32)
        out[..., ch] = np.interp(proj, positions, values)

    return Image.fromarray(out.astype(np.uint8), "RGB")


def _make_solid(width: int, height: int, color: str) -> Image.Image:
    return Image.new("RGB", (width, height), _hex_to_rgb(color))


def _make_diagonal_split(width: int, height: int, colors: list[str], angle_deg: float = 135) -> Image.Image:
    """대각선 분할 (할인 배너 스타일)"""
    a, b = colors[0], colors[1] if len(colors) > 1 else colors[0]
    img = Image.new("RGB", (width, height), _hex_to_rgb(a))
    draw = ImageDraw.Draw(img)
    # 단순화: 좌상 → 우하 삼각형 채우기
    rad = math.radians(angle_deg)
    dx, dy = math.cos(rad), math.sin(rad)
    # b 컬러 폴리곤
    if abs(dx) > abs(dy):
        # 가로 우세
        poly = [(width, 0), (width, height), (0, height)]
    else:
        poly = [(0, height), (width, height), (width, 0)]
    draw.polygon(poly, fill=_hex_to_rgb(b))
    return img


def _add_noise(img: Image.Image, intensity: float = 4) -> Image.Image:
    """미세 노이즈로 텍스처 추가 (스튜디오 느낌)"""
    arr = np.array(img, dtype=np.int16)
    noise = np.random.randint(-int(intensity), int(intensity) + 1, arr.shape, dtype=np.int16)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, img.mode)


def _add_vignette(img: Image.Image, strength: float = 0.25) -> Image.Image:
    """중앙 밝게, 외곽 어둡게 (스튜디오 조명 느낌)"""
    w, h = img.size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = w / 2, h / 2
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    d /= d.max()
    mask = 1 - strength * d ** 2
    arr = np.array(img, dtype=np.float32)
    for ch in range(arr.shape[2]):
        arr[..., ch] *= mask
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), img.mode)


def _add_spotlight(img: Image.Image, intensity: float = 0.15) -> Image.Image:
    """중앙 살짝 밝게 (제품 강조용)"""
    w, h = img.size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = w / 2, h * 0.55
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    d /= d.max()
    mask = 1 + intensity * np.exp(-d * 3)
    arr = np.array(img, dtype=np.float32)
    for ch in range(arr.shape[2]):
        arr[..., ch] = np.clip(arr[..., ch] * mask, 0, 255)
    return Image.fromarray(arr.astype(np.uint8), img.mode)


# ───────── BackgroundProvider 구현 ─────────

class MockBackgroundProvider(BackgroundProvider):
    """그라데이션/패턴 기반 로컬 배경"""

    def generate(self, width: int, height: int, concept: dict, seed: int = 0) -> Image.Image:
        random.seed(seed)
        np.random.seed(seed % (2**32))

        bg_cfg = concept.get("background", {})
        bg_type = bg_cfg.get("type", "gradient")
        colors = bg_cfg.get("colors", ["#FFFFFF", "#F0F0F0"])
        angle = float(bg_cfg.get("angle", 135))

        if bg_type == "solid":
            img = _make_solid(width, height, colors[0])
        elif bg_type == "diagonal_split":
            img = _make_diagonal_split(width, height, colors, angle)
        else:  # gradient
            img = _make_gradient(width, height, colors, angle)

        # 후처리: 노이즈 + 비네팅 + 스포트라이트
        img = _add_noise(img, intensity=3)
        img = _add_vignette(img, strength=0.18)
        img = _add_spotlight(img, intensity=0.10)

        return img


# ───────── TextSuggestionProvider 구현 ─────────

# 카테고리/컨셉별 문구 템플릿
_HEADLINE_BANK = {
    "health_food": ["하루 한 알의 건강", "내 몸을 위한 선택", "프리미엄 건강 라인", "오늘부터 시작"],
    "electronics": ["새로운 일상의 시작", "더 빠르게, 더 정확하게", "디테일이 다르다", "Pro급 성능"],
    "kitchen": ["주방의 품격", "오래 쓰는 진짜", "한 번 쓰면 인생템", "셰프의 선택"],
    "fashion": ["이 계절의 핫 아이템", "감성을 입다", "데일리 머스트해브", "트렌드 NEW"],
    "car": ["내 차의 업그레이드", "운전이 편해진다", "프로 드라이버 추천"],
    "pet": ["우리 아이 건강을 위해", "사랑하니까 더 좋은 걸", "수의사 추천"],
    "camping": ["자연으로 떠나는 시간", "캠퍼들의 선택", "가벼움과 견고함"],
    "beauty": ["피부가 달라진다", "오늘의 시그니처", "데일리 케어 완성"],
    "general": ["오늘의 추천", "이번 주 인기상품", "지금 가장 핫한", "MD 추천"],
}

_SUB_BANK = {
    "general": ["빠른 배송", "검증된 품질", "리뷰 검증", "당일 출고"],
    "health_food": ["국내 제조", "HACCP 인증", "고함량"],
    "electronics": ["1년 무상 A/S", "정품 정식 수입", "당일 발송"],
    "fashion": ["사이즈 다양", "당일 출고", "교환 무료"],
}

_BADGE_BANK = ["BEST", "NEW", "HOT", "MD's PICK", "리뷰 화제", "인기급상승"]


@lru_cache(maxsize=1)
def _all_forbidden_words() -> tuple[str, ...]:
    """모든 플랫폼 금지어의 합집합 (mock 추천 문구 자기검열용).

    플랫폼 인자가 suggest() 에 없으므로, 어떤 플랫폼에 올려도 안전하도록
    전 플랫폼 금지어를 모은다. 설정 로드 실패 시 빈 튜플 → 필터 미적용(안전 저하 없음)."""
    try:
        from app.services.concept_loader import get_platforms
        words: set[str] = set()
        for p in get_platforms().values():
            for w in (p.get("forbidden_words", []) or []):
                if w:
                    words.add(w)
        return tuple(words)
    except Exception:
        return ()


def _is_safe(text: str) -> bool:
    if not text:
        return True
    return not any(w in text for w in _all_forbidden_words())


def _pick_safe(candidates: list[str], fallback: str) -> str:
    """금지어가 없는 후보를 우선 선택. 전부 걸리면 fallback."""
    safe = [c for c in candidates if _is_safe(c)]
    if safe:
        return random.choice(safe)
    return fallback if _is_safe(fallback) else ""


class MockTextSuggestionProvider(TextSuggestionProvider):
    def suggest(self, category: str, concept: str, product_hint: Optional[str] = None) -> dict:
        headlines = _HEADLINE_BANK.get(category, _HEADLINE_BANK["general"])
        subs = _SUB_BANK.get(category, _SUB_BANK["general"])
        # 뱅크에 실수로 금지어가 섞여도 사후 필터로 걸러낸다
        return {
            "headline": _pick_safe(headlines, "오늘의 추천"),
            "sub_text": _pick_safe(subs, "빠른 배송"),
            "badge": _pick_safe(_BADGE_BANK, "NEW"),
        }


# ───────── QCProvider 구현 ─────────

class MockQCProvider(QCProvider):
    """규칙 기반 검수 (실제 AI 검수와 동일 인터페이스)"""

    def review(self, image: Image.Image, meta: dict) -> dict:
        notes: list[str] = []
        # 해상도 검수
        w, h = image.size
        if w < 600 or h < 600:
            notes.append("해상도가 600px 미만입니다")

        # 평균 밝기로 가독성 추정
        gray = np.array(image.convert("L"))
        mean_brightness = float(gray.mean())
        if mean_brightness < 30:
            notes.append("배경이 너무 어두워 가독성에 영향이 있을 수 있습니다")
        if mean_brightness > 245:
            notes.append("배경이 너무 밝아 흰색 텍스트가 보이지 않을 수 있습니다")

        # 대비 추정 (표준편차)
        contrast = float(gray.std())
        contrast_score = min(100, int(contrast * 1.5))

        passed = len(notes) == 0
        return {
            "passed": passed,
            "notes": notes,
            "text_legibility": 90 if passed else 70,
            "product_integrity": 100,  # 합성 방식이라 항상 100
            "contrast_score": contrast_score,
            "platform_compliance": True,
        }
