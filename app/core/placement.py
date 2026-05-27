"""
카테고리별 제품 배치 규칙

라이프스타일 신 위에 누끼 제품을 자연스럽게 올리기 위한 위치/크기/그림자 규칙.
제품 자체는 절대 변형하지 않고(원본 유지), 크기·위치·그림자만 카테고리에 맞게 조정한다.

anchor: 캔버스 내 세로 정렬 기준
  - "bottom": 바닥에 놓인 느낌(가구/식품/전자제품)
  - "center": 떠 있거나 진열된 느낌(의류/액세서리/뷰티)
  - "top":   상단 강조
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class PlacementRule:
    name: str
    anchor: str             # bottom | center | top
    size_ratio: float       # 캔버스 대비 제품 최대 비율(0~1)
    shadow_blur: int
    shadow_opacity: int     # 0~255
    shadow_offset_y: int
    harmonize: bool = True   # 배경과 색/명도 미세 조화


# 카테고리 기본값
_CATEGORY_DEFAULTS = {
    # 가구: 바닥에, 그림자 강하게(원근감)
    "가구": PlacementRule("furniture", "bottom", 0.66, 28, 130, 26),
    # 의류: 매달린 듯, 그림자 약하게
    "의류": PlacementRule("clothing", "center", 0.70, 16, 60, 10),
    # 식품: 식탁/카운터 위, 그림자 짧게
    "식품": PlacementRule("food", "bottom", 0.58, 16, 100, 12),
    # 전자제품: 데스크 위, 그림자 선명하게
    "전자제품": PlacementRule("electronics", "bottom", 0.60, 12, 140, 14),
    # 뷰티: 진열대, 그림자 부드럽게
    "뷰티": PlacementRule("beauty", "center", 0.52, 22, 80, 12),
    # 액세서리: 진열대 클로즈업, 그림자 디테일하게
    "액세서리": PlacementRule("accessory", "center", 0.50, 14, 110, 10),
    # 생활용품
    "생활용품": PlacementRule("household", "bottom", 0.60, 18, 100, 14),
    # 기타
    "기타": PlacementRule("default", "center", 0.62, 18, 100, 16),
}

# 하위 카테고리 미세 조정 (anchor/size override)
_SUB_OVERRIDES = {
    ("가구", "소파"): {"size_ratio": 0.70}, ("가구", "의자"): {"size_ratio": 0.62},
    ("가구", "테이블"): {"size_ratio": 0.68}, ("가구", "책상"): {"size_ratio": 0.68},
    ("가구", "책장"): {"size_ratio": 0.80, "anchor": "center"},
    ("가구", "옷장"): {"size_ratio": 0.80, "anchor": "center"},
    ("가구", "수납장"): {"size_ratio": 0.78, "anchor": "center"},
    ("의류", "상의"): {"size_ratio": 0.70, "anchor": "top"},
    ("의류", "원피스"): {"size_ratio": 0.72, "anchor": "top"},
    ("의류", "코트"): {"size_ratio": 0.72, "anchor": "top"},
    ("의류", "아우터"): {"size_ratio": 0.72, "anchor": "top"},
    ("의류", "신발"): {"size_ratio": 0.40, "anchor": "bottom", "shadow_opacity": 100},
}


def get_placement_rules(category: Optional[str], sub_category: Optional[str] = None) -> PlacementRule:
    """카테고리(+하위)별 배치 규칙. 미등록은 '기타' 기본값."""
    base = _CATEGORY_DEFAULTS.get(category or "기타", _CATEGORY_DEFAULTS["기타"])
    rule = PlacementRule(
        name=base.name, anchor=base.anchor, size_ratio=base.size_ratio,
        shadow_blur=base.shadow_blur, shadow_opacity=base.shadow_opacity,
        shadow_offset_y=base.shadow_offset_y, harmonize=base.harmonize,
    )
    ov = _SUB_OVERRIDES.get((category, sub_category))
    if ov:
        for k, v in ov.items():
            setattr(rule, k, v)
    return rule


def compute_position(rule: PlacementRule, canvas_w: int, canvas_h: int,
                     prod_w: int, prod_h: int) -> tuple[int, int]:
    """배치 규칙에 따른 제품 좌상단 좌표(가로 중앙 정렬, 세로는 anchor)."""
    px = (canvas_w - prod_w) // 2
    if rule.anchor == "bottom":
        py = int(canvas_h * 0.92) - prod_h          # 바닥 여백 8%
    elif rule.anchor == "top":
        py = int(canvas_h * 0.10)
    else:  # center
        py = (canvas_h - prod_h) // 2
    return px, max(0, py)
