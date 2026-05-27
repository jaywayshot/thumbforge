"""
신(scene) 프롬프트 생성 테스트 (실호출 없음)
─ 18 컨셉 × 8 카테고리 = 144 조합 프롬프트 생성
─ negative 에 'product' 포함(제품은 배경에 그리지 않음)
─ 제품 정보(공간/재질/색/무드) 영문 반영
─ scene 이미지 캐시 hit/miss
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image

from app.core import scene_cache
from app.core.scene_prompt import build_scene_prompt
from app.models.schemas import ProductInfo
from app.services.concept_loader import get_categories_v2, get_concept, get_concepts


def test_144_combinations():
    concepts = list(get_concepts().keys())
    cats = list(get_categories_v2().keys())
    assert len(concepts) == 18 and len(cats) == 8, f"{len(concepts)}x{len(cats)}"
    n = 0
    for cid in concepts:
        cobj = get_concept(cid)
        for cat in cats:
            pi = ProductInfo(category=cat)
            pos, neg = build_scene_prompt(pi, cobj, "coupang", concept_id=cid)
            assert pos and isinstance(pos, str) and len(pos) > 20
            assert "product" in neg, f"negative에 product 없음: {cid}/{cat}"
            assert "no product in frame" in pos  # 배경만 생성 지시
            n += 1
    assert n == 144
    print(f"  ✓ {n}개 조합 프롬프트 생성, negative 전부 'product' 차단")


def test_product_info_reflected():
    pi = ProductInfo(category="가구", sub_category="책상", material="원목",
                     color="화이트", use_space="서재", mood_keywords=["미니멀", "북유럽"])
    pos, neg = build_scene_prompt(pi, get_concept("white_minimal"), "coupang", concept_id="white_minimal")
    assert "solid wood" in pos       # 원목
    assert "study room" in pos       # 서재
    assert "white" in pos            # 화이트
    assert "scandinavian" in pos     # 북유럽
    print("  ✓ 제품 정보(재질/공간/색/무드) 영문 반영")


def test_clothing_negative_blocks_mannequin():
    pi = ProductInfo(category="의류", sub_category="코트")
    pos, neg = build_scene_prompt(pi, get_concept("smartstore_emotional"), "coupang", concept_id="smartstore_emotional")
    assert "mannequin" in neg
    print("  ✓ 의류 negative 에 mannequin 차단")


def test_reference_injected():
    pi = ProductInfo(category="뷰티")
    ref = {"dominant_hex": ["#E8D5C4"], "tone": "bright airy", "moods": ["vibrant colorful"]}
    pos, _ = build_scene_prompt(pi, get_concept("premium_luxury"), "coupang",
                                reference=ref, concept_id="premium_luxury")
    assert "#E8D5C4" in pos and "bright airy" in pos
    print("  ✓ 레퍼런스 색/톤/무드 주입")


def test_scene_cache_hit_miss(tmp_path=None):
    key = scene_cache.make_key("sig-test-xyz", "white_minimal", "coupang")
    img = Image.new("RGB", (64, 64), (200, 180, 160))
    # 초기에 없을 수도/있을 수도 → set 후 hit 보장
    scene_cache.set(key, img)
    got = scene_cache.get(key)
    assert got is not None and got.size == (64, 64)
    # TTL 만료
    future = __import__("time").time() + scene_cache.TTL_SECONDS + 10
    assert scene_cache.get(key, now=future) is None
    print("  ✓ scene 캐시 hit/miss/TTL")


if __name__ == "__main__":
    print("\n=== scene_prompt 테스트 ===")
    test_144_combinations()
    test_product_info_reflected()
    test_clothing_negative_blocks_mannequin()
    test_reference_injected()
    test_scene_cache_hit_miss()
    print("\n✅ scene_prompt 테스트 전체 통과")
