"""
Anthropic 문구 추천 Provider 테스트 (네트워크/비용 0)
─ 키 없을 때 mock 폴백
─ 금지어 system 프롬프트 주입
─ 정상 JSON / 본문 속 JSON 추출 / 파싱·호출 실패 폴백
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.settings import settings
from app.providers.anthropic_provider import (
    AnthropicTextSuggestionProvider,
    _gather_forbidden,
)


def _assert_valid(s: dict):
    assert isinstance(s, dict)
    for k in ("headline", "sub_text", "badge"):
        assert isinstance(s.get(k), str) and s[k].strip(), f"빈 값: {k}"


class _Block:
    def __init__(self, text):
        self.text = text


class _Resp:
    def __init__(self, text):
        self.content = [_Block(text)]


class _ClientOK:
    def __init__(self):
        self.messages = self
    def create(self, **kw):
        return _Resp('{"headline": "오늘의 특가", "sub_text": "당일 출고", "badge": "HOT"}')


class _ClientWrapped:
    """설명 문장 + JSON (본문 추출 검증)"""
    def __init__(self):
        self.messages = self
    def create(self, **kw):
        return _Resp('네, 여기 있습니다:\n{"headline": "감성 한 컷", "sub_text": "빠른 배송", "badge": "NEW"}\n감사합니다')


class _ClientBad:
    def __init__(self):
        self.messages = self
    def create(self, **kw):
        return _Resp("JSON 아님, 그냥 텍스트")


class _ClientRaise:
    def __init__(self):
        self.messages = self
    def create(self, **kw):
        raise RuntimeError("api error")


def test_fallback_without_key():
    saved = settings.anthropic_api_key
    settings.anthropic_api_key = ""
    try:
        p = AnthropicTextSuggestionProvider()
        assert p._client is None
        _assert_valid(p.suggest("beauty", "premium_luxury"))
        print("  ✓ 키 없음 → mock 폴백")
    finally:
        settings.anthropic_api_key = saved


def test_forbidden_injected():
    words = _gather_forbidden("beauty", "coupang_sales")
    assert "최저가" in words and "100%" in words
    sys_prompt = AnthropicTextSuggestionProvider()._system_prompt("beauty", "coupang_sales")
    assert "최저가" in sys_prompt
    print(f"  ✓ 금지어 {len(words)}개 system 주입")


def test_parse_ok():
    p = AnthropicTextSuggestionProvider()
    p._client = _ClientOK()
    out = p.suggest("beauty", "premium_luxury")
    _assert_valid(out)
    assert out["headline"] == "오늘의 특가" and out["badge"] == "HOT"
    print(f"  ✓ 정상 JSON: {out}")


def test_extract_json_from_prose():
    p = AnthropicTextSuggestionProvider()
    p._client = _ClientWrapped()
    out = p.suggest("beauty", "premium_luxury")
    _assert_valid(out)
    assert out["headline"] == "감성 한 컷"
    print(f"  ✓ 본문 속 JSON 추출: {out}")


def test_parse_failure_fallback():
    p = AnthropicTextSuggestionProvider()
    p._client = _ClientBad()
    _assert_valid(p.suggest("beauty", "premium_luxury"))
    print("  ✓ 파싱 실패 → mock 폴백")


def test_call_exception_fallback():
    p = AnthropicTextSuggestionProvider()
    p._client = _ClientRaise()
    _assert_valid(p.suggest("beauty", "premium_luxury"))
    print("  ✓ 호출 예외 → mock 폴백")


if __name__ == "__main__":
    print("\n=== Anthropic 문구 Provider 테스트 ===")
    test_fallback_without_key()
    test_forbidden_injected()
    test_parse_ok()
    test_extract_json_from_prose()
    test_parse_failure_fallback()
    test_call_exception_fallback()
    print("\n✅ Anthropic 문구 Provider 테스트 전체 통과")
