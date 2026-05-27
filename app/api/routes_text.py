"""LLM 문구 추천 + 사용량 라우트"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.providers import llm_usage
from app.providers.factory import get_text_provider
from app.settings import settings

router = APIRouter(prefix="/api", tags=["text"])


class TextSuggestRequest(BaseModel):
    category: str = "general"
    concept: str = "white_minimal"
    platform: Optional[str] = "coupang"
    product_hint: Optional[str] = None
    fresh: bool = False  # true 면 캐시 무시하고 새로 생성


@router.post("/text/suggest")
async def suggest_text(req: TextSuggestRequest) -> dict:
    """
    현재 카테고리/컨셉/플랫폼으로 매출형 문구를 추천한다.
    키가 없거나 호출 실패 시 자동으로 mock 폴백(에러 아님).
    """
    provider = get_text_provider()
    try:
        result = await run_in_threadpool(
            lambda: provider.suggest(
                category=req.category,
                concept=req.concept,
                product_hint=req.product_hint,
                platform=req.platform,
                fresh=req.fresh,
                use_cache=True,  # API 경로는 동일 조합 재요청을 캐시로 절약
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"문구 추천 실패: {e}")

    return {
        **result,
        "provider": (settings.text_provider or "mock").lower(),
    }


@router.get("/llm/usage")
async def llm_usage_stats() -> dict:
    """누적 LLM 사용량/비용 통계."""
    return llm_usage.read_stats()
