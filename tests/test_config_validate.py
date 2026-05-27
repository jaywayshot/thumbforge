"""
설정 무결성 검증 테스트
─ 실제 배포 config(concepts/platforms/categories)는 오류 0건이어야 함
─ 일부러 망가뜨린 입력에서 오류가 잡혀야 함
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.config_validate import (
    validate_config,
    validate_concepts,
    validate_categories,
    validate_platforms,
)


def test_shipped_config_is_clean():
    errors = validate_config()
    assert errors == [], "배포 config 오류:\n" + "\n".join(errors)
    print(f"  ✓ 배포 config 무결성 통과")


def test_bad_concept_detected():
    bad = {
        "broken": {
            "accent_color": "not-a-color",
            "background": {"type": "hologram", "colors": ["#FFF", "zzz"]},
            "layout": "nonexistent_layout",
            "headline_max": -3,
        }
    }
    errors = validate_concepts(bad)
    joined = "\n".join(errors)
    assert "accent_color" in joined
    assert "background.type" in joined
    assert "background.colors" in joined
    assert "layout" in joined
    assert "headline_max" in joined
    print(f"  ✓ 잘못된 컨셉에서 오류 {len(errors)}건 검출")


def test_bad_category_reference_detected():
    concepts = {"white_minimal": {}}
    cats = {"x": {"recommended_concepts": ["white_minimal", "ghost_concept"],
                  "default_layout": "no_such_layout"}}
    errors = validate_categories(cats, concepts)
    joined = "\n".join(errors)
    assert "ghost_concept" in joined
    assert "default_layout" in joined
    print(f"  ✓ 카테고리 잘못된 참조 검출")


def test_bad_platform_sizes_detected():
    bad = {"p": {"sizes": {"thumbnail": [1000], "detail": "big"}}}
    errors = validate_platforms(bad)
    assert len(errors) == 2, errors
    print(f"  ✓ 플랫폼 잘못된 sizes 검출")


if __name__ == "__main__":
    print("\n=== 설정 무결성 검증 테스트 ===")
    test_shipped_config_is_clean()
    test_bad_concept_detected()
    test_bad_category_reference_detected()
    test_bad_platform_sizes_detected()
    print("\n✅ 설정 검증 테스트 전체 통과")
