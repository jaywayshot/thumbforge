"""
레이아웃 엔진
── 제품 배치 영역(box) + 텍스트 배치 영역(box) 계산
── 컨셉의 layout 값으로 선택
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Box:
    x: int
    y: int
    w: int
    h: int

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)


@dataclass
class Layout:
    name: str
    product_box: Box
    headline_box: Box
    sub_box: Box
    badge_anchor: tuple[int, int]   # 좌상단 기준
    discount_anchor: tuple[int, int]


def build_layout(name: str, canvas_w: int, canvas_h: int) -> Layout:
    """
    canvas 안에서 제품/텍스트 영역 계산
    화면 비율은 1:1 기준으로 비율 좌표 사용
    """
    W, H = canvas_w, canvas_h

    if name == "left_product_right_text":
        product = Box(int(W * 0.05), int(H * 0.10), int(W * 0.50), int(H * 0.80))
        headline = Box(int(W * 0.58), int(H * 0.20), int(W * 0.38), int(H * 0.30))
        sub = Box(int(W * 0.58), int(H * 0.55), int(W * 0.38), int(H * 0.15))
        badge = (int(W * 0.58), int(H * 0.10))
        discount = (int(W * 0.82), int(H * 0.80))

    elif name == "center_product":
        product = Box(int(W * 0.15), int(H * 0.18), int(W * 0.70), int(H * 0.62))
        headline = Box(int(W * 0.05), int(H * 0.82), int(W * 0.90), int(H * 0.10))
        sub = Box(int(W * 0.10), int(H * 0.92), int(W * 0.80), int(H * 0.06))
        badge = (int(W * 0.04), int(H * 0.04))
        discount = (int(W * 0.84), int(H * 0.16))

    elif name == "center_product_top_text":
        headline = Box(int(W * 0.05), int(H * 0.05), int(W * 0.90), int(H * 0.15))
        sub = Box(int(W * 0.10), int(H * 0.20), int(W * 0.80), int(H * 0.06))
        product = Box(int(W * 0.12), int(H * 0.30), int(W * 0.76), int(H * 0.62))
        badge = (int(W * 0.04), int(H * 0.04))
        discount = (int(W * 0.84), int(H * 0.84))

    elif name == "huge_text_top":
        headline = Box(int(W * 0.05), int(H * 0.04), int(W * 0.90), int(H * 0.30))
        sub = Box(int(W * 0.10), int(H * 0.34), int(W * 0.80), int(H * 0.06))
        product = Box(int(W * 0.18), int(H * 0.42), int(W * 0.64), int(H * 0.50))
        badge = (int(W * 0.04), int(H * 0.04))
        discount = (int(W * 0.78), int(H * 0.72))

    elif name == "huge_center_product":
        product = Box(int(W * 0.08), int(H * 0.10), int(W * 0.84), int(H * 0.68))
        headline = Box(int(W * 0.05), int(H * 0.80), int(W * 0.90), int(H * 0.10))
        sub = Box(int(W * 0.15), int(H * 0.91), int(W * 0.70), int(H * 0.06))
        badge = (int(W * 0.04), int(H * 0.04))
        discount = (int(W * 0.84), int(H * 0.08))

    elif name == "diagonal":
        product = Box(int(W * 0.30), int(H * 0.10), int(W * 0.65), int(H * 0.80))
        headline = Box(int(W * 0.04), int(H * 0.40), int(W * 0.40), int(H * 0.25))
        sub = Box(int(W * 0.04), int(H * 0.66), int(W * 0.40), int(H * 0.10))
        badge = (int(W * 0.04), int(H * 0.06))
        discount = (int(W * 0.80), int(H * 0.78))

    else:  # 기본
        product = Box(int(W * 0.15), int(H * 0.18), int(W * 0.70), int(H * 0.62))
        headline = Box(int(W * 0.05), int(H * 0.82), int(W * 0.90), int(H * 0.10))
        sub = Box(int(W * 0.10), int(H * 0.92), int(W * 0.80), int(H * 0.06))
        badge = (int(W * 0.04), int(H * 0.04))
        discount = (int(W * 0.84), int(H * 0.16))

    return Layout(
        name=name,
        product_box=product,
        headline_box=headline,
        sub_box=sub,
        badge_anchor=badge,
        discount_anchor=discount,
    )


# 컨셉 → 가능한 레이아웃 다양화 (variant 자동 생성용)
LAYOUT_VARIANTS = {
    "left_product_right_text": ["left_product_right_text", "center_product", "diagonal"],
    "center_product": ["center_product", "center_product_top_text", "huge_center_product"],
    "center_product_top_text": ["center_product_top_text", "center_product", "huge_text_top"],
    "huge_text_top": ["huge_text_top", "center_product_top_text", "diagonal"],
    "huge_center_product": ["huge_center_product", "center_product", "center_product_top_text"],
    "diagonal": ["diagonal", "left_product_right_text", "center_product"],
}


def variants_for(layout_name: str) -> list[str]:
    return LAYOUT_VARIANTS.get(layout_name, [layout_name, "center_product", "center_product_top_text"])
