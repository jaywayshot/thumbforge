"""
LLM 문구 품질 평가 도구 (수동 실행 전용)

8개 컨셉 × 4개 카테고리 = 32개 조합을 자동 호출해 결과를 표로 정리한다.
─ 캐시는 무시하고 호출(정확한 측정) → use_cache=False
─ 각 응답에 대해: 글자수 초과 / 금지어 포함 / 카테고리 적합도(키워드 휴리스틱)
─ 결과를 workspace/temp/llm_eval.md 로 저장 → 사람이 눈으로 검수

주의: 실제 LLM 키가 있으면 32회 실호출 → 비용이 발생한다.
      그래서 mock 이 아닌 provider 는 실행 전 사용자 확인을 받는다(--yes 로 생략).

사용법:
  python scripts/eval_llm_quality.py                 # TEXT_PROVIDER(.env) 사용
  python scripts/eval_llm_quality.py --provider openai
  python scripts/eval_llm_quality.py --provider anthropic --yes
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.providers.llm_support import MAX_BADGE, MAX_HEADLINE, MAX_SUB, gather_forbidden
from app.services.concept_loader import get_categories
from app.settings import settings

# 평가 대상 (8 컨셉 × 4 카테고리 = 32)
CONCEPTS = [
    "coupang_sales", "premium_luxury", "white_minimal", "tech_electronics",
    "discount_event", "smartstore_emotional", "kids", "apple_style",
]
CATEGORIES = ["electronics", "beauty", "health_food", "fashion"]
PLATFORM = "coupang"


def _get_provider(name: str):
    name = (name or "mock").lower()
    if name == "openai":
        from app.providers.openai_provider import OpenAITextSuggestionProvider
        return OpenAITextSuggestionProvider(), name
    if name == "anthropic":
        from app.providers.anthropic_provider import AnthropicTextSuggestionProvider
        return AnthropicTextSuggestionProvider(), name
    from app.providers.mock import MockTextSuggestionProvider
    return MockTextSuggestionProvider(), "mock"


def _category_fit(text: str, category: str) -> int:
    """카테고리 키워드가 문구에 몇 개 등장하는지(약한 휴리스틱)."""
    cat = get_categories().get(category, {}) or {}
    kws = list(cat.get("keywords", []) or []) + [cat.get("label", "")]
    return sum(1 for kw in kws if kw and kw in text)


def _eval_one(result: dict, category: str, concept: str) -> dict:
    forbidden = gather_forbidden(category, concept, PLATFORM)
    joined = " ".join(str(result.get(k, "")) for k in ("headline", "sub_text", "badge"))
    over = []
    if len(result.get("headline", "")) > MAX_HEADLINE:
        over.append("headline")
    if len(result.get("sub_text", "")) > MAX_SUB:
        over.append("sub_text")
    if len(result.get("badge", "")) > MAX_BADGE:
        over.append("badge")
    hits = [w for w in forbidden if w and w in joined]
    return {
        "over_length": over,
        "forbidden": hits,
        "fit": _category_fit(joined, category),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="LLM 문구 품질 평가 (32 조합)")
    ap.add_argument("--provider", default=settings.text_provider or "mock",
                    help="openai | anthropic | mock (기본: .env TEXT_PROVIDER)")
    ap.add_argument("--yes", action="store_true", help="실호출 확인 프롬프트 생략")
    args = ap.parse_args()

    provider, pname = _get_provider(args.provider)
    is_live = pname in ("openai", "anthropic") and getattr(provider, "_client", None) is not None

    print(f"평가 provider: {pname} (실호출={'예' if is_live else '아니오(키 없음→mock 폴백)'})")
    print(f"대상: {len(CONCEPTS)}컨셉 × {len(CATEGORIES)}카테고리 = "
          f"{len(CONCEPTS) * len(CATEGORIES)}회, 캐시 무시")

    if is_live and not args.yes:
        ans = input("실제 API를 32회 호출하면 비용이 발생합니다. 진행할까요? [y/N] ").strip().lower()
        if ans != "y":
            print("취소했습니다.")
            return

    rows = []
    t0 = time.time()
    for concept in CONCEPTS:
        for category in CATEGORIES:
            res = provider.suggest(
                category=category, concept=concept,
                platform=PLATFORM, use_cache=False,  # 평가는 캐시 무시
            )
            ev = _eval_one(res, category, concept)
            rows.append((concept, category, res, ev))
            flag = "⚠" if (ev["over_length"] or ev["forbidden"]) else "✓"
            print(f"  {flag} {concept:<20} {category:<12} "
                  f"{res.get('headline')} / {res.get('sub_text')} / {res.get('badge')}")

    elapsed = time.time() - t0

    # 마크다운 표 저장
    out_path = settings.temp_path / "llm_eval.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    over_cnt = sum(1 for *_, ev in rows if ev["over_length"])
    forb_cnt = sum(1 for *_, ev in rows if ev["forbidden"])

    lines = [
        f"# LLM 문구 품질 평가 — provider={pname}",
        "",
        f"- 조합: {len(rows)}개 (캐시 무시)",
        f"- 실호출: {'예' if is_live else '아니오(mock 폴백)'}",
        f"- 소요: {elapsed:.1f}s",
        f"- 글자수 초과: {over_cnt}건 / 금지어 포함: {forb_cnt}건",
        "",
        "| 컨셉 | 카테고리 | 헤드라인 | 서브 | 뱃지 | 길이초과 | 금지어 | 적합도 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for concept, category, res, ev in rows:
        over = ",".join(ev["over_length"]) or "-"
        forb = ",".join(ev["forbidden"]) or "-"
        lines.append(
            f"| {concept} | {category} | {res.get('headline')} | {res.get('sub_text')} | "
            f"{res.get('badge')} | {over} | {forb} | {ev['fit']} |"
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\n결과 저장: {out_path}")
    print(f"요약 → 글자수 초과 {over_cnt}건, 금지어 {forb_cnt}건 (총 {len(rows)}건)")


if __name__ == "__main__":
    main()
