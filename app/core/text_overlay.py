"""
텍스트 / 뱃지 오버레이
── 한글 폰트 자동 탐지 (Windows/Mac/Linux 모두 시도)
── 폰트 없으면 PIL 기본 폰트로 폴백 (영문만 출력)
── 외곽선 / 그림자 / 가독성 보정 포함
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont


# 후보 한글 폰트 (각 OS별)
_FONT_CANDIDATES = [
    # Windows
    "C:/Windows/Fonts/malgun.ttf",
    "C:/Windows/Fonts/malgunbd.ttf",
    "C:/Windows/Fonts/NanumGothic.ttf",
    "C:/Windows/Fonts/NanumGothicBold.ttf",
    # macOS
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/Library/Fonts/AppleGothic.ttf",
    # Linux
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]


@lru_cache(maxsize=64)
def _load_font_cached(path: str, size: int) -> ImageFont.FreeTypeFont:
    """캐시된 폰트 로드"""
    try:
        return ImageFont.truetype(path, size=size)
    except Exception:
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()


@lru_cache(maxsize=64)
def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """가능한 한글 지원 폰트 찾기, 없으면 PIL 기본"""
    # 사용자가 직접 ./assets/fonts/ 에 폰트 넣어둔 경우 우선
    project_fonts = Path(__file__).resolve().parent.parent.parent / "assets" / "fonts"
    user_candidates = []
    if project_fonts.exists():
        for ext in ("*.ttf", "*.otf", "*.ttc"):
            user_candidates.extend(sorted(project_fonts.glob(ext)))

    bold_keywords = ("bold", "bd", "black", "heavy")
    candidates = [str(p) for p in user_candidates] + _FONT_CANDIDATES

    # bold 우선 매칭
    if bold:
        bold_first = [c for c in candidates if any(k in c.lower() for k in bold_keywords)]
        others = [c for c in candidates if c not in bold_first]
        candidates = bold_first + others

    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            continue

    # 폴백
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    """안전한 텍스트 크기 측정"""
    try:
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        return (r - l, b - t)
    except Exception:
        return draw.textsize(text, font=font)


def draw_text_with_shadow(
    img: Image.Image,
    text: str,
    position: tuple[int, int],
    font: ImageFont.ImageFont,
    color: str,
    shadow: bool = True,
    shadow_color: str = "#000000",
    stroke_width: int = 0,
    stroke_color: Optional[str] = None,
    anchor: str = "lt",
) -> None:
    """그림자 + 외곽선까지 한 번에"""
    draw = ImageDraw.Draw(img, "RGBA")
    x, y = position
    if shadow:
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(sh)
        try:
            sdraw.text((x + 2, y + 2), text, font=font, fill=shadow_color + "80" if len(shadow_color) == 7 else shadow_color, anchor=anchor)
        except TypeError:
            sdraw.text((x + 2, y + 2), text, font=font, fill=shadow_color, anchor=anchor)
        sh = sh.filter(ImageFilter.GaussianBlur(radius=3))
        img.alpha_composite(sh)
    kwargs = {"font": font, "fill": color, "anchor": anchor}
    if stroke_width > 0 and stroke_color is not None:
        kwargs["stroke_width"] = stroke_width
        kwargs["stroke_fill"] = stroke_color
    draw.text((x, y), text, **kwargs)


def draw_pill_badge(
    img: Image.Image,
    text: str,
    position: tuple[int, int],
    font: ImageFont.ImageFont,
    bg_color: str,
    text_color: str = "#FFFFFF",
    padding_x: int = 24,
    padding_y: int = 12,
) -> tuple[int, int, int, int]:
    """알약 모양 뱃지. 위치는 좌상단 기준. 반환: 그려진 영역(x0,y0,x1,y1)"""
    draw = ImageDraw.Draw(img, "RGBA")
    tw, th = _text_size(draw, text, font)
    w, h = tw + padding_x * 2, th + padding_y * 2
    x, y = position
    r = h // 2
    # 그림자
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(sh)
    sdraw.rounded_rectangle((x + 3, y + 3, x + w + 3, y + h + 3), radius=r, fill=(0, 0, 0, 60))
    sh = sh.filter(ImageFilter.GaussianBlur(radius=5))
    img.alpha_composite(sh)
    # 본체
    draw.rounded_rectangle((x, y, x + w, y + h), radius=r, fill=bg_color)
    draw.text((x + padding_x, y + padding_y - 2), text, font=font, fill=text_color)
    return (x, y, x + w, y + h)


def draw_discount_burst(
    img: Image.Image,
    discount_percent: int,
    center: tuple[int, int],
    size: int,
    bg_color: str = "#FF3B30",
    text_color: str = "#FFFFFF",
) -> None:
    """별 모양 폭발 뱃지 (할인%용)"""
    import math
    draw = ImageDraw.Draw(img, "RGBA")
    cx, cy = center
    points = []
    spikes = 12
    for i in range(spikes * 2):
        r = size if i % 2 == 0 else size * 0.78
        a = (math.pi / spikes) * i - math.pi / 2
        points.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    draw.polygon(points, fill=bg_color)

    font = _load_font(int(size * 0.4), bold=True)
    text = f"{discount_percent}%"
    tw, th = _text_size(draw, text, font)
    draw.text((cx - tw // 2, cy - th // 2 - int(size * 0.06)), text, font=font, fill=text_color)
    small = _load_font(int(size * 0.18), bold=True)
    sw, sh_ = _text_size(draw, "할인", small)
    draw.text((cx - sw // 2, cy + int(size * 0.18)), "할인", font=small, fill=text_color)


def get_font(size: int, bold: bool = False, brand_font_path: Optional[str] = None) -> ImageFont.FreeTypeFont:
    """브랜드 폰트가 지정되면 그것을 최우선 사용"""
    if brand_font_path:
        try:
            return _load_font_cached(brand_font_path, size)
        except Exception:
            pass
    return _load_font(size, bold)
