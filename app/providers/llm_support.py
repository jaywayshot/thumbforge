"""
LLM 문구 추천 공통 지원 모듈 (OpenAI / Anthropic provider 공유)

여기에 모은 것:
─ 컨셉별 톤 가이드라인(18개 전부)
─ 한글 문구 길이 제약 상수
─ 금지어 수집 (카테고리/컨셉/플랫폼 → platforms.yaml 동적 로드)
─ system/user 프롬프트 빌더
─ JSON 관대 파서
─ 응답 검증·보정(누락 채움, 길이 초과 잘라내기, 금지어 검출)
─ 토큰 비용 추정
─ 검증·재호출 오케스트레이터 (두 provider 가 동일 레이어를 쓰도록)

provider 들은 "원시 호출(complete)"만 구현하고 나머지 검증/재호출은 이 모듈에 위임한다.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("thumbforge")

# ───────── 길이 제약 (한글 기준) ─────────
MAX_HEADLINE = 12
MAX_SUB = 16
MAX_BADGE = 6
MAX_TOKENS = 300  # 한 호출당 응답 토큰 상한 (비용 폭주 방지)

_FIELD_LIMITS = (("headline", MAX_HEADLINE), ("sub_text", MAX_SUB), ("badge", MAX_BADGE))

# ───────── 컨셉별 톤 가이드 (18개) ─────────
TONE_GUIDE: Dict[str, str] = {
    "coupang_sales": "직설적이고 가격을 강조. 헤드라인 5-8자, 즉시 구매 욕구 자극.",
    "smartstore_emotional": "감성적이고 따뜻한 어조. 라이프스타일 연상, 부드러운 단어.",
    "premium_luxury": "절제되고 고급스럽게. 영문 단어 허용, 헤드라인 3-6자, 군더더기 없이.",
    "black_luxury": "딥블랙 무드, 카리스마 있는 절제된 표현. 영문 가능, 짧게.",
    "white_minimal": "여백을 살리는 짧은 단어. 헤드라인 2-4자, 핵심 한 단어 위주.",
    "tech_electronics": "스펙·기능·성능 강조. 숫자(배수/시간/용량) 활용, 신뢰감 있는 어조.",
    "health_food": "건강·신뢰 강조. 성분/인증 느낌, 과장 없이 사실 기반.",
    "female_emotional": "여성 타깃 감성. 로즈/플로럴 무드, 셀프케어·자기만족 표현.",
    "instagram_aesthetic": "인스타 감성, 트렌디·필름톤. 영문 해시태그 느낌의 짧은 카피.",
    "discount_event": "강렬한 할인 강조. 헤드라인 4-7자, 숫자/퍼센트·한정 느낌.",
    "seasonal_event": "시즌·기념일 분위기. 시의성 있는 표현, 따뜻하거나 들뜬 어조.",
    "summer": "시원함·청량감. 여름·바다·쿨 키워드, 가볍고 산뜻하게.",
    "winter": "포근함·차분함. 겨울·따뜻함·연말 무드, 절제된 감성.",
    "kids": "밝고 친근하게. 부모 시선의 안심+아이 시선의 즐거움, 둥근 어조.",
    "sports": "역동적·강한 어조. 동기부여·퍼포먼스 강조, 짧고 임팩트 있게.",
    "brand_shop": "균형 잡힌 브랜드 톤. 신뢰·완성도, 과하지 않은 세련됨.",
    "homeshopping": "긴급·한정 강조. 거대 가격/수량 임박, 강한 행동 유도.",
    "apple_style": "미니멀·세련. 헤드라인 2-5자, 큰 여백 전제의 한 마디.",
}
_DEFAULT_TONE = "간결하고 매출 전환에 효과적인 한글 카피. 군더더기 없이 핵심만."


def tone_for(concept: str) -> str:
    return TONE_GUIDE.get(concept, _DEFAULT_TONE)


# ───────── 금지어 수집 ─────────

def gather_forbidden(category: str, concept: str, platform: Optional[str] = None) -> List[str]:
    """
    컨셉/카테고리 금지어 + 플랫폼 금지어를 합쳐 순서 보존 중복 제거.

    platform 이 주어지면 그 플랫폼만, 없으면 모든 플랫폼 금지어의 합집합
    (어느 플랫폼에 올려도 안전하도록).
    """
    from app.services.concept_loader import get_categories, get_concept, get_platforms

    words: List[str] = []
    try:
        words += list((get_concept(concept) or {}).get("forbidden_words", []) or [])
    except Exception:
        pass
    try:
        words += list((get_categories().get(category, {}) or {}).get("forbidden_words", []) or [])
    except Exception:
        pass
    try:
        platforms = get_platforms()
        if platform and platform in platforms:
            words += list(platforms[platform].get("forbidden_words", []) or [])
        else:
            for p in platforms.values():
                words += list(p.get("forbidden_words", []) or [])
    except Exception:
        pass

    seen: set = set()
    uniq: List[str] = []
    for w in words:
        if w and w not in seen:
            seen.add(w)
            uniq.append(w)
    return uniq


# ───────── 프롬프트 빌더 ─────────

def build_system_prompt(
    category: str,
    concept: str,
    platform: Optional[str],
    forbidden: List[str],
    *,
    strict: bool = False,
    forbidden_hits: Optional[List[str]] = None,
) -> str:
    forbidden_str = ", ".join(forbidden) if forbidden else "(없음)"
    base = (
        "너는 한국 쇼핑몰 썸네일 카피라이터다. 제품 썸네일에 들어갈 매출 전환형 문구를 만든다.\n"
        f"카테고리 맥락: {category}\n"
        f"컨셉 톤 가이드: {tone_for(concept)}\n"
        "반드시 아래 키만 가진 JSON 객체 하나만 출력한다(코드블록/설명/그 외 텍스트 금지): "
        '{"headline": "...", "sub_text": "...", "badge": "..."}\n'
        f"- headline: {MAX_HEADLINE}자 이내, 강렬한 한글 헤드라인\n"
        f"- sub_text: {MAX_SUB}자 이내, 배송/품질 등 사실 기반 보조 문구\n"
        f"- badge: {MAX_BADGE}자 이내, BEST/NEW/HOT 같은 짧은 뱃지(한글/영문)\n"
        f"절대 사용 금지 단어/표현(법적·정책적 위험): {forbidden_str}. "
        "변형 포함 어떤 형태로도 쓰지 마라.\n"
        "객관적으로 입증 불가능한 과장(최고/유일/100% 등)도 쓰지 마라."
    )
    if strict:
        hits = ", ".join(forbidden_hits) if forbidden_hits else forbidden_str
        base += (
            "\n\n[재작성 지시] 직전 응답에 금지 표현이 포함되었다. "
            f"특히 다음 표현은 절대 쓰지 마라: {hits}. "
            "금지어를 완전히 배제하고 다시 작성하라."
        )
    return base


def build_user_prompt(
    category: str, concept: str, platform: Optional[str], product_hint: Optional[str]
) -> str:
    parts = [f"카테고리: {category}", f"컨셉: {concept}"]
    if platform:
        parts.append(f"업로드 플랫폼: {platform}")
    if product_hint:
        parts.append(f"제품 힌트: {product_hint}")
    return "\n".join(parts) + "\n위 정보에 맞는 문구 JSON을 생성해라."


# ───────── JSON 파싱 / 검증 ─────────

def loads_lenient(text: str) -> dict:
    """순수 JSON 우선, 실패 시 본문에서 첫 { ... } 블록 추출."""
    if text is None:
        raise ValueError("빈 응답")
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            raise
        return json.loads(m.group(0))


def contains_forbidden(result: Dict[str, str], forbidden: List[str]) -> List[str]:
    joined = " ".join(str(result.get(k, "")) for k in ("headline", "sub_text", "badge"))
    return [w for w in forbidden if w and w in joined]


def validate_and_fix(
    data: dict, forbidden: List[str], fill: Dict[str, str]
) -> Tuple[Dict[str, str], List[str]]:
    """
    응답 검증·보정:
    ─ 누락/빈 필드 → fill(mock) 값으로 채움 (issue: missing:<field>)
    ─ 길이 초과 → 잘라내기 + 경고 로깅 (issue: truncated:<field>)
    ─ 금지어 포함 → issue 'forbidden' (잘라낸 최종 문자열 기준)
    """
    issues: List[str] = []
    out: Dict[str, str] = {}
    for key, limit in _FIELD_LIMITS:
        v = str(data.get(key) or "").strip()
        if not v:
            v = fill.get(key, "")
            issues.append(f"missing:{key}")
        if len(v) > limit:
            logger.warning("[llm] %s 길이 초과(%d>%d) 잘라냄: %r", key, len(v), limit, v)
            v = v[:limit]
            issues.append(f"truncated:{key}")
        out[key] = v

    if contains_forbidden(out, forbidden):
        issues.append("forbidden")
    return out, issues


# ───────── 토큰 비용 추정 (USD, 1M 토큰당) ─────────
_PRICES: Dict[str, Tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "claude-sonnet-4-5": (3.0, 15.0),
}


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """모델별 대략 비용(USD). 미등록 모델은 0.0(미상)."""
    price = _PRICES.get(model)
    if not price:
        # 접두 매칭(버전 접미사 대응)
        for k, v in _PRICES.items():
            if model.startswith(k):
                price = v
                break
    if not price:
        return 0.0
    pin, pout = price
    return round(prompt_tokens / 1_000_000 * pin + completion_tokens / 1_000_000 * pout, 8)


# ───────── 검증·재호출 오케스트레이터 ─────────

# complete(strict, forbidden_hits) -> (raw_text, prompt_tokens, completion_tokens)
CompleteFn = Callable[[bool, Optional[List[str]]], Tuple[str, int, int]]


def generate_with_validation(
    *,
    complete: CompleteFn,
    forbidden: List[str],
    fill: Dict[str, str],
    provider_name: str,
    model: str,
    allow_regen: bool = True,
) -> Optional[Dict[str, str]]:
    """
    1) complete(strict=False) 호출 → JSON 파싱(실패 시 None=폴백)
    2) 검증·보정 후 금지어 없으면 반환
    3) 금지어 있으면 complete(strict=True)로 1회 재호출 → 그래도 금지어면 None(폴백)
    각 실제 호출마다 사용량을 기록한다.
    """
    from app.providers import llm_usage

    try:
        raw, ptok, ctok = complete(False, None)
        data = loads_lenient(raw)
        if not isinstance(data, dict):
            raise ValueError("JSON 객체가 아님")
    except Exception as e:
        logger.warning("[%s] 문구 생성/파싱 실패 → mock 폴백: %s", provider_name, e)
        return None

    result, issues = validate_and_fix(data, forbidden, fill)
    llm_usage.record(
        provider_name, model, ptok, ctok,
        cost_usd=estimate_cost_usd(model, ptok, ctok), regenerated=False,
    )
    if "forbidden" not in issues:
        return result
    if not allow_regen:
        return None

    # 금지어 포함 → 1회 재호출(regenerate)
    hits = contains_forbidden(result, forbidden)
    logger.warning("[%s] 금지어 검출 %s → 1회 재호출", provider_name, hits)
    try:
        raw2, ptok2, ctok2 = complete(True, hits)
        data2 = loads_lenient(raw2)
        if not isinstance(data2, dict):
            raise ValueError("JSON 객체가 아님")
    except Exception as e:
        logger.warning("[%s] 재호출 실패 → mock 폴백: %s", provider_name, e)
        return None

    result2, issues2 = validate_and_fix(data2, forbidden, fill)
    llm_usage.record(
        provider_name, model, ptok2, ctok2,
        cost_usd=estimate_cost_usd(model, ptok2, ctok2), regenerated=True,
    )
    if "forbidden" not in issues2:
        return result2
    logger.warning("[%s] 재호출 후에도 금지어 잔존 → mock 폴백", provider_name)
    return None
