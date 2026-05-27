"""
OpenAI 문구 추천 Provider 테스트
─ 키 없을 때 mock 폴백 검증 (핵심)
─ 금지어가 system 프롬프트에 주입되는지 검증
─ 키가 있어도 호출/파싱 실패 시 mock 폴백 검증 (가짜 클라이언트 주입)
─ 정상 JSON 응답 정규화 검증

실제 OpenAI API를 호출하지 않는다 (네트워크/비용 0).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import os
os.environ.setdefault("WORKSPACE_DIR", str(ROOT / "workspace"))

from app.settings import settings
from app.providers.openai_provider import OpenAITextSuggestionProvider


def _assert_valid_suggestion(s: dict):
    assert isinstance(s, dict)
    for key in ("headline", "sub_text", "badge"):
        assert key in s, f"키 누락: {key}"
        assert isinstance(s[key], str) and s[key].strip(), f"빈 값: {key}"


def test_fallback_without_key():
    """OPENAI_API_KEY 가 없으면 실제 호출 없이 mock 폴백."""
    saved = settings.openai_api_key
    settings.openai_api_key = ""
    try:
        provider = OpenAITextSuggestionProvider()
        assert provider._client is None, "키 없는데 클라이언트가 생성됨"
        out = provider.suggest(category="electronics", concept="tech_electronics")
        _assert_valid_suggestion(out)
        print(f"  ✓ 키 없음 → mock 폴백: {out}")
    finally:
        settings.openai_api_key = saved


def test_forbidden_words_injected():
    """플랫폼 금지어가 system 프롬프트에 주입되는지."""
    provider = OpenAITextSuggestionProvider()
    words = provider._gather_forbidden("electronics", "coupang_sales")
    # 쿠팡/스마트스토어 등에 공통으로 있는 금지어가 포함돼야 함
    assert "최저가" in words and "100%" in words, f"금지어 누락: {words}"
    messages = provider._build_messages("electronics", "coupang_sales", None)
    system = messages[0]["content"]
    assert "최저가" in system, "system 프롬프트에 금지어 미주입"
    assert messages[0]["role"] == "system" and messages[1]["role"] == "user"
    print(f"  ✓ 금지어 {len(words)}개 수집 + system 프롬프트 주입 확인")


class _FakeMsg:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})


class _FakeResp:
    def __init__(self, content):
        self.choices = [_FakeMsg(content)]


class _FakeClientOK:
    """정상 JSON 반환"""
    def __init__(self):
        self.chat = type("C", (), {"completions": self})()
    def create(self, **kwargs):
        return _FakeResp('{"headline": "오늘의 특가", "sub_text": "당일 출고", "badge": "HOT"}')


class _FakeClientBad:
    """JSON 아닌 쓰레기 반환 → 파싱 실패 유도"""
    def __init__(self):
        self.chat = type("C", (), {"completions": self})()
    def create(self, **kwargs):
        return _FakeResp("이건 JSON이 아니에요 헤헤")


class _FakeClientRaise:
    """호출 자체가 예외"""
    def __init__(self):
        self.chat = type("C", (), {"completions": self})()
    def create(self, **kwargs):
        raise RuntimeError("network down")


def test_parse_ok():
    provider = OpenAITextSuggestionProvider()
    provider._client = _FakeClientOK()
    out = provider.suggest("electronics", "tech_electronics")
    _assert_valid_suggestion(out)
    assert out["headline"] == "오늘의 특가"
    assert out["badge"] == "HOT"
    print(f"  ✓ 정상 JSON 정규화: {out}")


def test_parse_failure_fallback():
    """파싱 실패해도 예외로 죽지 않고 mock 폴백."""
    provider = OpenAITextSuggestionProvider()
    provider._client = _FakeClientBad()
    out = provider.suggest("electronics", "tech_electronics")
    _assert_valid_suggestion(out)
    print(f"  ✓ 파싱 실패 → mock 폴백: {out}")


def test_call_exception_fallback():
    provider = OpenAITextSuggestionProvider()
    provider._client = _FakeClientRaise()
    out = provider.suggest("electronics", "tech_electronics")
    _assert_valid_suggestion(out)
    print(f"  ✓ 호출 예외 → mock 폴백: {out}")


if __name__ == "__main__":
    print("\n=== OpenAI 문구 Provider 테스트 ===")
    test_fallback_without_key()
    test_forbidden_words_injected()
    test_parse_ok()
    test_parse_failure_fallback()
    test_call_exception_fallback()
    print("\n✅ OpenAI 문구 Provider 테스트 전체 통과")
