"""
설정(YAML) 무결성 검증기

concepts.yaml / platforms.yaml / categories.yaml 의 흔한 실수를 잡는다:
─ 컨셉: 색상 hex 형식, background.type, layout 이름, headline_max
─ 카테고리: recommended_concepts 가 실제 컨셉을 가리키는지, default_layout 유효성
─ 플랫폼: sizes 가 [w, h] 형태인지

오류 문자열 리스트를 반환한다(빈 리스트 = 정상). 예외를 던지지 않으므로
서버 기동 시/CI 에서 가볍게 호출할 수 있다.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from app.core.layout import LAYOUT_VARIANTS

VALID_LAYOUTS = set(LAYOUT_VARIANTS.keys())
VALID_BG_TYPES = {"gradient", "solid", "diagonal_split"}
_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _is_hex(value: Any) -> bool:
    return isinstance(value, str) and bool(_HEX_RE.match(value))


def validate_concepts(concepts: Dict[str, Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    if not concepts:
        return ["concepts 가 비어 있습니다"]
    for name, c in concepts.items():
        where = f"concept '{name}'"
        if not isinstance(c, dict):
            errors.append(f"{where}: 매핑이 아닙니다")
            continue

        # 색상
        for color_key in ("accent_color", "sub_color", "text_color"):
            if color_key in c and not _is_hex(c[color_key]):
                errors.append(f"{where}: {color_key} 가 hex 색상이 아님 ({c.get(color_key)!r})")

        # 배경
        bg = c.get("background", {})
        if not isinstance(bg, dict):
            errors.append(f"{where}: background 가 매핑이 아님")
        else:
            bt = bg.get("type", "gradient")
            if bt not in VALID_BG_TYPES:
                errors.append(f"{where}: background.type '{bt}' 미지원 (가능: {sorted(VALID_BG_TYPES)})")
            colors = bg.get("colors", [])
            if not isinstance(colors, list) or not colors:
                errors.append(f"{where}: background.colors 가 비었거나 리스트가 아님")
            else:
                for col in colors:
                    if not _is_hex(col):
                        errors.append(f"{where}: background.colors 에 잘못된 hex {col!r}")

        # 레이아웃
        layout = c.get("layout", "center_product")
        if layout not in VALID_LAYOUTS:
            errors.append(f"{where}: layout '{layout}' 미지원 (가능: {sorted(VALID_LAYOUTS)})")

        # headline_max
        hm = c.get("headline_max", 14)
        if not isinstance(hm, int) or hm <= 0:
            errors.append(f"{where}: headline_max 는 양의 정수여야 함 ({hm!r})")
    return errors


def validate_categories(
    categories: Dict[str, Dict[str, Any]], concepts: Dict[str, Dict[str, Any]]
) -> List[str]:
    errors: List[str] = []
    concept_names = set(concepts.keys())
    for name, cat in categories.items():
        where = f"category '{name}'"
        if not isinstance(cat, dict):
            errors.append(f"{where}: 매핑이 아닙니다")
            continue
        for rec in cat.get("recommended_concepts", []) or []:
            if rec not in concept_names:
                errors.append(f"{where}: recommended_concepts 의 '{rec}' 가 존재하지 않는 컨셉")
        dl = cat.get("default_layout")
        if dl is not None and dl not in VALID_LAYOUTS:
            errors.append(f"{where}: default_layout '{dl}' 미지원")
    return errors


def validate_platforms(platforms: Dict[str, Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    if not platforms:
        return ["platforms 가 비어 있습니다"]
    for name, p in platforms.items():
        where = f"platform '{name}'"
        if not isinstance(p, dict):
            errors.append(f"{where}: 매핑이 아닙니다")
            continue
        sizes = p.get("sizes", {})
        if not isinstance(sizes, dict):
            errors.append(f"{where}: sizes 가 매핑이 아님")
            continue
        for size_name, dims in sizes.items():
            if not (isinstance(dims, (list, tuple)) and len(dims) == 2
                    and all(isinstance(d, int) and d > 0 for d in dims)):
                errors.append(f"{where}: sizes.{size_name} 는 [w, h] 양의 정수쌍이어야 함 ({dims!r})")
    return errors


def validate_config() -> List[str]:
    """실제 로드된 config 전체 검증. 오류 문자열 리스트 반환(빈 리스트=정상)."""
    from app.services.concept_loader import (
        get_categories,
        get_concepts,
        get_platforms,
    )

    concepts = get_concepts()
    errors = validate_concepts(concepts)
    errors += validate_categories(get_categories(), concepts)
    errors += validate_platforms(get_platforms())
    return errors


if __name__ == "__main__":
    errs = validate_config()
    if errs:
        print(f"❌ 설정 오류 {len(errs)}건:")
        for e in errs:
            print(f"  - {e}")
        raise SystemExit(1)
    print("✅ 설정 무결성 검증 통과")
