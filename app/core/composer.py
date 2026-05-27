"""
컴포저 - 모든 요소를 하나의 썸네일로 합성
── 핵심 원칙: 제품 원본 훼손 금지
  · 누끼된 제품 이미지는 절대로 AI가 다시 그리지 않음
  · 크기 / 위치 / 그림자만 조정
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from app.core.layout import Box, Layout
from app.core.placement import PlacementRule, compute_position
from app.core.text_overlay import (
    draw_text_with_shadow,
    draw_pill_badge,
    draw_discount_burst,
    get_font,
    _text_size,
)


# ───────── 제품 배치 ─────────

def fit_product_to_box(product_rgba: Image.Image, box: Box, max_ratio: float = 0.95) -> tuple[Image.Image, tuple[int, int]]:
    """
    제품 이미지를 box 안에 비율 유지하며 가장 크게 맞춤
    제품을 다시 그리는 게 아니라 크기/위치만 조정 → 원본 유지
    반환: (리사이즈된 제품, 좌상단 좌표)
    """
    if product_rgba.mode != "RGBA":
        product_rgba = product_rgba.convert("RGBA")

    # 알파 영역으로 실제 컨텐츠 박스 측정
    alpha = np.array(product_rgba.split()[-1])
    ys, xs = np.where(alpha > 10)
    if len(xs) == 0:
        # 알파가 없으면 전체 사용
        x0, y0, x1, y1 = 0, 0, product_rgba.width, product_rgba.height
    else:
        x0, y0 = int(xs.min()), int(ys.min())
        x1, y1 = int(xs.max()) + 1, int(ys.max()) + 1

    cropped = product_rgba.crop((x0, y0, x1, y1))
    cw, ch = cropped.size

    target_w = int(box.w * max_ratio)
    target_h = int(box.h * max_ratio)
    scale = min(target_w / cw, target_h / ch)
    new_w, new_h = max(1, int(cw * scale)), max(1, int(ch * scale))
    resized = cropped.resize((new_w, new_h), Image.LANCZOS)

    # box 중앙 정렬
    px = box.x + (box.w - new_w) // 2
    py = box.y + (box.h - new_h) // 2
    return resized, (px, py)


def _crop_to_alpha(product_rgba: Image.Image) -> Image.Image:
    if product_rgba.mode != "RGBA":
        product_rgba = product_rgba.convert("RGBA")
    alpha = np.array(product_rgba.split()[-1])
    ys, xs = np.where(alpha > 10)
    if len(xs) == 0:
        return product_rgba
    return product_rgba.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))


def fit_product_by_placement(
    product_rgba: Image.Image, canvas_w: int, canvas_h: int, rule: PlacementRule
) -> tuple[Image.Image, tuple[int, int]]:
    """카테고리 배치 규칙에 따라 제품 크기/위치 결정 (원본은 리사이즈만)."""
    cropped = _crop_to_alpha(product_rgba)
    cw, ch = cropped.size
    target = max(1, int(min(canvas_w, canvas_h) * rule.size_ratio))
    scale = min(target / cw, target / ch)
    new_w, new_h = max(1, int(cw * scale)), max(1, int(ch * scale))
    resized = cropped.resize((new_w, new_h), Image.LANCZOS)
    pos = compute_position(rule, canvas_w, canvas_h, new_w, new_h)
    return resized, pos


def harmonize_with_background(product_rgba: Image.Image, background: Image.Image) -> Image.Image:
    """제품 명도/채도를 배경과 어울리게 ±5% 미세 조정(원형 보존, 알파 유지)."""
    prod = product_rgba.convert("RGBA")
    r, g, b, a = prod.split()
    rgb = Image.merge("RGB", (r, g, b))

    bg_lum = float(np.asarray(background.convert("L"), dtype=np.float32).mean())
    pa = np.asarray(a)
    mask = pa > 10
    if mask.sum() == 0:
        return product_rgba
    prod_lum = float(np.asarray(rgb.convert("L"), dtype=np.float32)[mask].mean())

    factor = 1.0
    if prod_lum > 1:
        factor = max(0.95, min(1.05, bg_lum / prod_lum))  # ±5% clamp
    rgb = ImageEnhance.Brightness(rgb).enhance(factor)
    rgb = ImageEnhance.Color(rgb).enhance(0.97)  # 채도 살짝 낮춰 배경과 조화
    return Image.merge("RGBA", (*rgb.split(), a))


def make_drop_shadow(product_rgba: Image.Image, blur: int = 20, opacity: int = 110, offset_y: int = 15) -> Image.Image:
    """제품 알파 기반 그림자 생성"""
    alpha = product_rgba.split()[-1]
    # 그림자 = 알파를 검정으로
    shadow_full = Image.new("RGBA", product_rgba.size, (0, 0, 0, 0))
    shadow_full.putalpha(alpha)
    # 검정 컬러 채우기
    black = Image.new("RGBA", product_rgba.size, (0, 0, 0, 0))
    black.paste((0, 0, 0, opacity), mask=alpha)
    return black.filter(ImageFilter.GaussianBlur(radius=blur))


def paste_product_with_shadow(canvas: Image.Image, product: Image.Image, position: tuple[int, int]) -> None:
    """그림자 → 제품 순으로 합성"""
    shadow = make_drop_shadow(product, blur=18, opacity=90, offset_y=18)
    x, y = position
    canvas.alpha_composite(shadow, (x, y + 18))
    canvas.alpha_composite(product, (x, y))


def paste_logo(canvas: Image.Image, logo_path, max_ratio: float = 0.12, margin_ratio: float = 0.03) -> None:
    """우상단에 브랜드 로고 워터마크"""
    try:
        logo = Image.open(logo_path).convert("RGBA")
    except Exception:
        return
    cw, ch = canvas.size
    target_w = int(cw * max_ratio)
    scale = target_w / logo.width
    new_size = (target_w, max(1, int(logo.height * scale)))
    logo = logo.resize(new_size, Image.LANCZOS)
    margin = int(cw * margin_ratio)
    pos = (cw - logo.width - margin, margin)
    canvas.alpha_composite(logo, pos)


# ───────── 컨셉별 폰트 크기 자동 결정 ─────────

def _fit_text_to_box(text: str, box: Box, bold: bool = True, max_size: int = 120, min_size: int = 18, padding: int = 8, font_path: Optional[str] = None) -> int:
    """문구를 box 안에 들어가게 폰트 크기 자동 결정"""
    if not text:
        return min_size
    from PIL import ImageDraw
    test_img = Image.new("RGBA", (10, 10))
    draw = ImageDraw.Draw(test_img)
    size = max_size
    while size > min_size:
        font = get_font(size, bold=bold, brand_font_path=font_path)
        tw, th = _text_size(draw, text, font)
        if tw <= box.w - padding * 2 and th <= box.h - padding * 2:
            return size
        size -= 2
    return min_size


# ───────── 메인 컴포지트 ─────────

def compose_thumbnail(
    background: Image.Image,
    product_rgba: Image.Image,
    layout: Layout,
    concept: dict,
    headline: Optional[str] = None,
    sub_text: Optional[str] = None,
    badge: Optional[str] = None,
    discount_percent: Optional[int] = None,
    logo_path: Optional[object] = None,   # Path or str
    font_path: Optional[object] = None,   # 브랜드 폰트 우선
    placement: Optional[PlacementRule] = None,  # 카테고리별 배치 규칙(있으면 우선)
) -> Image.Image:
    """
    배경 + 제품 + 텍스트 → 최종 썸네일 RGBA
    """
    if background.mode != "RGBA":
        background = background.convert("RGBA")
    canvas = background.copy()

    bfp = str(font_path) if font_path else None

    # 1. 제품 배치 (제품은 절대 변형 X, 리사이즈/위치만)
    if placement is not None:
        # 카테고리별 배치: 배경과 색 조화 후 anchor/크기/그림자 규칙 적용
        prod_src = harmonize_with_background(product_rgba, background) if placement.harmonize else product_rgba
        product_fitted, pos = fit_product_by_placement(prod_src, canvas.width, canvas.height, placement)
        shadow = make_drop_shadow(product_fitted, blur=placement.shadow_blur,
                                  opacity=placement.shadow_opacity, offset_y=placement.shadow_offset_y)
        canvas.alpha_composite(shadow, (pos[0], pos[1] + placement.shadow_offset_y))
        canvas.alpha_composite(product_fitted, pos)
    else:
        product_fitted, pos = fit_product_to_box(product_rgba, layout.product_box, max_ratio=0.96)
        paste_product_with_shadow(canvas, product_fitted, pos)

    # 2. 텍스트
    text_color = concept.get("text_color", "#1A1A1A")
    accent = concept.get("accent_color", "#FF3B30")
    sub_color = concept.get("sub_color", "#888888")

    if headline:
        size = _fit_text_to_box(headline, layout.headline_box, bold=True, max_size=int(layout.headline_box.h * 0.85), font_path=bfp)
        font = get_font(size, bold=True, brand_font_path=bfp)
        draw_text_with_shadow(
            canvas,
            headline,
            (layout.headline_box.x, layout.headline_box.y),
            font=font,
            color=text_color,
            shadow=True,
            stroke_width=0,
        )

    if sub_text:
        size = _fit_text_to_box(sub_text, layout.sub_box, bold=False, max_size=int(layout.sub_box.h * 0.85), font_path=bfp)
        font = get_font(size, bold=False, brand_font_path=bfp)
        draw_text_with_shadow(
            canvas,
            sub_text,
            (layout.sub_box.x, layout.sub_box.y),
            font=font,
            color=sub_color,
            shadow=False,
        )

    # 3. 뱃지
    if badge:
        badge_font = get_font(max(20, layout.product_box.h // 22), bold=True, brand_font_path=bfp)
        draw_pill_badge(
            canvas,
            badge,
            layout.badge_anchor,
            font=badge_font,
            bg_color=accent,
            text_color="#FFFFFF",
        )

    # 4. 할인 폭발 뱃지
    if discount_percent and discount_percent > 0:
        size = max(80, canvas.width // 7)
        draw_discount_burst(
            canvas,
            discount_percent,
            layout.discount_anchor,
            size=size,
            bg_color=accent,
            text_color="#FFFFFF",
        )

    # 5. 브랜드 로고 워터마크 (최상단 레이어)
    if logo_path:
        paste_logo(canvas, logo_path, max_ratio=0.12, margin_ratio=0.03)

    return canvas
