"""
Mock 문구 추천기 금지어 회귀 테스트
─ 모든 카테고리에서 반복 추천해도 플랫폼 금지어가 새지 않아야 함
─ 사후 필터(_pick_safe)가 전부 금지어인 후보에서 fallback 으로 빠지는지
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.providers.mock import (
    MockTextSuggestionProvider,
    _HEADLINE_BANK,
    _all_forbidden_words,
    _is_safe,
    _pick_safe,
)


def test_forbidden_union_loaded():
    words = _all_forbidden_words()
    # platforms.yaml 에 정의된 대표 금지어가 잡혀야 함
    assert "최저가" in words and "100%" in words and "완벽" in words and "1위" in words
    print(f"  ✓ 금지어 합집합 {len(words)}개 로드")


def test_no_forbidden_in_suggestions():
    provider = MockTextSuggestionProvider()
    forbidden = _all_forbidden_words()
    categories = list(_HEADLINE_BANK.keys()) + ["unknown_cat"]  # unknown → general 폴백
    leaks = []
    for cat in categories:
        for _ in range(50):  # 랜덤 선택을 충분히 커버
            s = provider.suggest(cat, "coupang_sales")
            blob = " ".join(str(s[k]) for k in ("headline", "sub_text", "badge"))
            for w in forbidden:
                if w in blob:
                    leaks.append((cat, w, blob))
    assert not leaks, f"금지어 누출: {leaks[:5]}"
    print(f"  ✓ {len(categories)}개 카테고리 × 50회 추천 — 금지어 누출 0")


def test_bank_itself_clean():
    """뱅크에 직접 박힌 값에도 금지어가 없어야 한다(사후필터 의존 최소화)."""
    forbidden = _all_forbidden_words()
    dirty = []
    for cat, items in _HEADLINE_BANK.items():
        for h in items:
            for w in forbidden:
                if w in h:
                    dirty.append((cat, h, w))
    assert not dirty, f"헤드라인 뱅크에 금지어: {dirty}"
    print("  ✓ 헤드라인 뱅크 자체 클린")


def test_pick_safe_fallback():
    # 모든 후보가 금지어면 fallback 으로
    out = _pick_safe(["최저가 특가", "100% 보장"], fallback="오늘의 추천")
    assert _is_safe(out), f"fallback 도 안전하지 않음: {out}"
    assert out == "오늘의 추천"
    print(f"  ✓ 전부 금지어 → fallback: {out}")


if __name__ == "__main__":
    print("\n=== Mock 문구 금지어 회귀 테스트 ===")
    test_forbidden_union_loaded()
    test_bank_itself_clean()
    test_no_forbidden_in_suggestions()
    test_pick_safe_fallback()
    print("\n✅ Mock 문구 금지어 테스트 전체 통과")
