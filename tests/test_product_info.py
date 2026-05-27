"""ProductInfo 스키마 검증 (빈 값/부분 입력/캐시 시그니처)"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.models.schemas import GenerateRequest, ProductInfo


def test_defaults():
    pi = ProductInfo()
    assert pi.category == "기타"
    assert pi.product_name is None and pi.mood_keywords is None
    assert pi.size_w is None
    print("  ✓ 기본값(빈 값 허용, category=기타)")


def test_partial_and_signature():
    a = ProductInfo(category="가구", material="원목", color="화이트")
    b = ProductInfo(category="가구", material="원목", color="화이트")
    c = ProductInfo(category="의류", material="원목", color="화이트")
    assert a.cache_signature() == b.cache_signature()
    assert a.cache_signature() != c.cache_signature()
    print(f"  ✓ cache_signature 동일/구분: {a.cache_signature()}")


def test_generate_request_optional():
    # product_info 없이도 GenerateRequest 생성 가능(기존 호환), 기본 variants=1
    r = GenerateRequest(upload_id="x")
    assert r.product_info is None and r.variants == 1 and r.fresh is False
    # product_info 포함
    r2 = GenerateRequest(upload_id="x", product_info=ProductInfo(category="식품"))
    assert r2.product_info.category == "식품"
    print("  ✓ GenerateRequest.product_info 선택적 + 기본 variants=1")


def test_size_label_alternative():
    pi = ProductInfo(category="의류", size_label="L")
    assert pi.size_label == "L" and pi.size_w is None
    print("  ✓ 사이즈 모를 때 S/M/L 대체")


if __name__ == "__main__":
    print("\n=== ProductInfo 테스트 ===")
    test_defaults()
    test_partial_and_signature()
    test_generate_request_optional()
    test_size_label_alternative()
    print("\n✅ ProductInfo 테스트 전체 통과")
