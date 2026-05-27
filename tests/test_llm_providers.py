"""
LLM 문구 추천 깊이 구현 테스트 (네트워크/비용 0 — 가짜 클라이언트 주입)

검증 범위
─ 키 없을 때 mock 폴백 (openai/anthropic)
─ JSON 파싱 실패 → mock 폴백
─ 글자수 초과 → 잘라내기
─ 누락 필드 → mock 값으로 채움
─ 금지어 포함 → 1회 재호출 → (정상화) / (계속 금지어면 mock 폴백)
─ 캐시 hit/miss / TTL / 1MB 제거 / 키 구분
─ 사용량 기록 + 통계
─ 비용 추정
─ system 프롬프트에 톤 가이드/길이/금지어 주입
─ API: POST /api/text/suggest, GET /api/llm/usage
─ (옵트인) RUN_LIVE_LLM_TEST=true 일 때만 실제 1회 호출 + 비용 상한 검증
"""
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.providers import llm_cache, llm_usage, llm_support
from app.providers.anthropic_provider import AnthropicTextSuggestionProvider
from app.providers.openai_provider import OpenAITextSuggestionProvider
from app.settings import settings


# ───────── 가짜 클라이언트 ─────────

def _oai_resp(content: str, ptok=12, ctok=8):
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=content))],
        usage=types.SimpleNamespace(prompt_tokens=ptok, completion_tokens=ctok),
    )


class _OAIClient:
    """contents 리스트를 순서대로 반환(마지막 값 반복)."""
    def __init__(self, contents):
        self.contents = contents
        self.calls = 0
        self.chat = types.SimpleNamespace(completions=self)

    def create(self, **kw):
        c = self.contents[min(self.calls, len(self.contents) - 1)]
        self.calls += 1
        return _oai_resp(c)


def _ant_resp(text: str):
    return types.SimpleNamespace(
        content=[types.SimpleNamespace(text=text)],
        usage=types.SimpleNamespace(input_tokens=12, output_tokens=8),
    )


class _AntClient:
    def __init__(self, texts):
        self.texts = texts
        self.calls = 0
        self.messages = self

    def create(self, **kw):
        t = self.texts[min(self.calls, len(self.texts) - 1)]
        self.calls += 1
        return _ant_resp(t)


def _valid(s: dict):
    assert isinstance(s, dict)
    for k in ("headline", "sub_text", "badge"):
        assert isinstance(s.get(k), str) and s[k].strip(), f"빈 값: {k}"


def _oai():
    p = OpenAITextSuggestionProvider()
    return p


# ───────── 폴백 ─────────

def test_openai_fallback_without_key():
    saved = settings.openai_api_key
    settings.openai_api_key = ""
    try:
        p = OpenAITextSuggestionProvider()
        assert p._client is None
        _valid(p.suggest("electronics", "tech_electronics"))
        print("  ✓ OpenAI 키 없음 → mock 폴백")
    finally:
        settings.openai_api_key = saved


def test_anthropic_fallback_without_key():
    saved = settings.anthropic_api_key
    settings.anthropic_api_key = ""
    try:
        p = AnthropicTextSuggestionProvider()
        assert p._client is None
        _valid(p.suggest("beauty", "premium_luxury"))
        print("  ✓ Anthropic 키 없음 → mock 폴백")
    finally:
        settings.anthropic_api_key = saved


def test_parse_failure_fallback():
    p = _oai()
    p._client = _OAIClient(["이건 JSON이 아니다"])
    _valid(p.suggest("electronics", "tech_electronics"))
    print("  ✓ 파싱 실패 → mock 폴백")


# ───────── 검증 레이어 ─────────

def test_truncate_over_length():
    p = _oai()
    long_head = "가" * 30
    long_sub = "나" * 30
    long_badge = "다" * 30
    import json
    p._client = _OAIClient([json.dumps(
        {"headline": long_head, "sub_text": long_sub, "badge": long_badge},
        ensure_ascii=False)])
    out = p.suggest("electronics", "tech_electronics")
    assert len(out["headline"]) == llm_support.MAX_HEADLINE
    assert len(out["sub_text"]) == llm_support.MAX_SUB
    assert len(out["badge"]) == llm_support.MAX_BADGE
    print(f"  ✓ 글자수 초과 잘라내기: {len(out['headline'])}/{len(out['sub_text'])}/{len(out['badge'])}")


def test_missing_field_filled():
    import json
    p = _oai()
    p._client = _OAIClient([json.dumps({"headline": "특가 시작"}, ensure_ascii=False)])
    out = p.suggest("electronics", "tech_electronics")
    _valid(out)  # 누락된 sub_text/badge 가 mock 으로 채워져 비어있지 않아야 함
    assert out["headline"] == "특가 시작"
    print(f"  ✓ 누락 필드 mock 보충: {out}")


def test_forbidden_regenerate_then_clean():
    import json
    p = _oai()
    bad = json.dumps({"headline": "최저가 보장", "sub_text": "당일출고", "badge": "HOT"}, ensure_ascii=False)
    good = json.dumps({"headline": "오늘의 특가", "sub_text": "당일출고", "badge": "HOT"}, ensure_ascii=False)
    p._client = _OAIClient([bad, good])
    out = p.suggest("electronics", "coupang_sales")
    assert p._client.calls == 2, "금지어 검출 시 1회 재호출해야 함"
    assert "최저가" not in " ".join(out.values())
    assert out["headline"] == "오늘의 특가"
    print(f"  ✓ 금지어 → 재호출 후 정상화: {out} (호출 {p._client.calls}회)")


def test_forbidden_persist_fallback():
    import json
    p = _oai()
    bad = json.dumps({"headline": "최저가 1위", "sub_text": "당일출고", "badge": "HOT"}, ensure_ascii=False)
    p._client = _OAIClient([bad, bad])  # 두 번 다 금지어
    out = p.suggest("electronics", "coupang_sales")
    assert p._client.calls == 2
    forbidden = llm_support.gather_forbidden("electronics", "coupang_sales", "coupang")
    assert not any(w in " ".join(out.values()) for w in forbidden), out
    print(f"  ✓ 재호출 후에도 금지어 → mock 폴백: {out}")


def test_anthropic_prose_json_and_validate():
    p = AnthropicTextSuggestionProvider()
    p._client = _AntClient(['설명...\n{"headline":"감성 한 컷","sub_text":"빠른 배송","badge":"NEW"}\n끝'])
    out = p.suggest("beauty", "premium_luxury")
    assert out["headline"] == "감성 한 컷"
    print(f"  ✓ Anthropic 본문 속 JSON 추출+검증: {out}")


# ───────── 프롬프트 ─────────

def test_system_prompt_has_tone_and_limits():
    sys_prompt = AnthropicTextSuggestionProvider()._system_prompt("electronics", "tech_electronics", "coupang")
    assert llm_support.TONE_GUIDE["tech_electronics"][:6] in sys_prompt  # 톤 가이드 일부
    assert str(llm_support.MAX_HEADLINE) in sys_prompt
    assert "최저가" in sys_prompt  # 금지어 주입
    print("  ✓ system 프롬프트: 톤 가이드 + 길이 + 금지어 주입")


# ───────── 비용 추정 ─────────

def test_cost_estimate():
    c = llm_support.estimate_cost_usd("gpt-4o-mini", 1_000_000, 1_000_000)
    assert abs(c - (0.15 + 0.60)) < 1e-6, c
    assert llm_support.estimate_cost_usd("unknown-model", 1000, 1000) == 0.0
    # 접두 매칭
    assert llm_support.estimate_cost_usd("claude-haiku-4-5-20251001", 1_000_000, 0) == 1.0
    print(f"  ✓ 비용 추정: gpt-4o-mini 1M+1M = ${c}")


# ───────── 캐시 ─────────

def test_cache_roundtrip_ttl(tmp_path=None):
    path = (Path(tmp_path) / "lc.json") if tmp_path else (ROOT / "workspace" / "temp" / "_test_llm_cache.json")
    if path.exists():
        path.unlink()
    args = ("openai", "gpt-4o-mini", "electronics", "tech_electronics", "coupang")
    payload = {"headline": "테스트", "sub_text": "서브", "badge": "NEW"}
    assert llm_cache.get(*args, cache_path=path) is None
    llm_cache.set(*args, payload, cache_path=path)
    assert llm_cache.get(*args, cache_path=path) == payload
    # TTL 만료
    future = __import__("time").time() + llm_cache.TTL_SECONDS + 10
    assert llm_cache.get(*args, cache_path=path, now=future) is None
    print("  ✓ 캐시 저장/조회/TTL")


def test_cache_key_distinguishes_provider():
    a = llm_cache.make_key("openai", "m", "c", "k", "p")
    b = llm_cache.make_key("anthropic", "m", "c", "k", "p")
    assert a != b
    print("  ✓ provider 별 캐시 키 구분")


def test_cache_eviction_over_1mb():
    # 1MB 넘게 채우면 오래된 항목부터 제거되어 1MB 이하 유지
    data = {}
    big = "x" * 2000
    for i in range(800):
        data[f"k{i}"] = {"ts": i, "result": {"headline": big}}
    pruned = llm_cache._evict_if_needed(data)
    import json
    size = len(json.dumps(pruned, ensure_ascii=False).encode("utf-8"))
    assert size <= llm_cache.MAX_BYTES, size
    assert len(pruned) < len(data)  # 일부 제거됨
    # 남은 것은 최신(ts 큰) 쪽
    remaining = sorted(int(k[1:]) for k in pruned)
    assert remaining[-1] == 799
    print(f"  ✓ 1MB 초과 제거: {len(data)}→{len(pruned)}개, {size}B")


def test_provider_cache_hit_miss(tmp_path=None):
    import json
    tmp = Path(tmp_path) if tmp_path else (ROOT / "workspace" / "temp")
    cache_file = tmp / "_test_provider_cache.json"
    if cache_file.exists():
        cache_file.unlink()
    orig = llm_cache._default_path
    llm_cache._default_path = lambda: cache_file
    try:
        p = _oai()
        p._client = _OAIClient([json.dumps(
            {"headline": "캐시테스트", "sub_text": "서브", "badge": "NEW"}, ensure_ascii=False)])
        # 1차: miss → 클라이언트 호출 + 캐시 저장
        out1 = p.suggest("__cat__", "__concept__", platform="coupang", use_cache=True)
        assert p._client.calls == 1
        # 2차: hit → 클라이언트 추가 호출 없음
        out2 = p.suggest("__cat__", "__concept__", platform="coupang", use_cache=True)
        assert p._client.calls == 1, "캐시 적중인데 재호출됨"
        assert out1 == out2
        # fresh=True → 캐시 무시하고 재호출
        out3 = p.suggest("__cat__", "__concept__", platform="coupang", use_cache=True, fresh=True)
        assert p._client.calls == 2
        print(f"  ✓ provider 캐시 hit/miss/fresh: calls={p._client.calls}")
    finally:
        llm_cache._default_path = orig


# ───────── 사용량 ─────────

def test_usage_record_and_stats(tmp_path=None):
    tmp = Path(tmp_path) if tmp_path else (ROOT / "workspace" / "temp")
    usage_file = tmp / "_test_usage.jsonl"
    if usage_file.exists():
        usage_file.unlink()
    llm_usage.record("openai", "gpt-4o-mini", 100, 50, cost_usd=0.0001, usage_path=usage_file)
    llm_usage.record("openai", "gpt-4o-mini", 200, 80, cost_usd=0.0002, cached=False, usage_path=usage_file)
    llm_usage.record("openai", "gpt-4o-mini", 0, 0, cached=True, usage_path=usage_file)
    stats = llm_usage.read_stats(usage_path=usage_file)
    assert stats["total_calls"] == 3
    assert stats["live_calls"] == 2 and stats["cached_calls"] == 1
    assert stats["prompt_tokens"] == 300 and stats["completion_tokens"] == 130
    assert abs(stats["cost_usd"] - 0.0003) < 1e-9
    assert "gpt-4o-mini" in stats["by_model"]
    print(f"  ✓ 사용량 기록/통계: {stats['total_calls']}콜, ${stats['cost_usd']}")


# ───────── API ─────────

def test_api_text_suggest_and_usage():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    r = client.post("/api/text/suggest", json={
        "category": "electronics", "concept": "tech_electronics", "platform": "coupang"})
    assert r.status_code == 200, r.text
    body = r.json()
    for k in ("headline", "sub_text", "badge", "provider"):
        assert k in body
    u = client.get("/api/llm/usage")
    assert u.status_code == 200
    assert "total_calls" in u.json()
    print(f"  ✓ API /text/suggest + /llm/usage: provider={body['provider']}")


# ───────── 실호출 (옵트인) ─────────

def test_live_llm_optional():
    if os.environ.get("RUN_LIVE_LLM_TEST") != "true":
        print("  · (skip) 실호출은 RUN_LIVE_LLM_TEST=true 일 때만")
        return
    import time
    for name, has_key, make in (
        ("openai", bool(settings.openai_api_key), OpenAITextSuggestionProvider),
        ("anthropic", bool(settings.anthropic_api_key), AnthropicTextSuggestionProvider),
    ):
        if not has_key:
            print(f"  · (skip) {name} 키 없음")
            continue
        p = make()
        usage_before = llm_usage.read_stats()["cost_usd"]
        t0 = time.time()
        out = p.suggest("electronics", "tech_electronics", platform="coupang", fresh=True, use_cache=False)
        _valid(out)
        spent = llm_usage.read_stats()["cost_usd"] - usage_before
        assert spent < 0.01, f"{name} 호출 비용이 1센트 초과: ${spent}"
        print(f"  ✓ LIVE {name}: {out} ({time.time()-t0:.1f}s, +${spent:.6f})")


if __name__ == "__main__":
    print("\n=== LLM 문구 Provider 깊이 테스트 ===")
    test_openai_fallback_without_key()
    test_anthropic_fallback_without_key()
    test_parse_failure_fallback()
    test_truncate_over_length()
    test_missing_field_filled()
    test_forbidden_regenerate_then_clean()
    test_forbidden_persist_fallback()
    test_anthropic_prose_json_and_validate()
    test_system_prompt_has_tone_and_limits()
    test_cost_estimate()
    test_cache_roundtrip_ttl()
    test_cache_key_distinguishes_provider()
    test_cache_eviction_over_1mb()
    test_provider_cache_hit_miss()
    test_usage_record_and_stats()
    test_api_text_suggest_and_usage()
    test_live_llm_optional()
    print("\n✅ LLM 문구 Provider 테스트 전체 통과")
