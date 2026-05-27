"""경쟁사 분석 라우트"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.analyzers.cache import get_cached, set_cached
from app.analyzers.competitor import (
    DEFAULT_MAX_ITEMS,
    HARD_MAX_ITEMS,
    RobotsBlockedError,
    analyze_competitor,
)
from app.analyzers.sites import supported_sites

router = APIRouter(prefix="/api/analyze", tags=["analyze"])


@router.get("/sites")
async def list_supported_sites() -> dict:
    """인식 가능한 사이트 목록 (UI 안내용)."""
    return {"sites": supported_sites()}


class CompetitorRequest(BaseModel):
    url: str
    max_items: int = Field(default=DEFAULT_MAX_ITEMS, ge=1, le=HARD_MAX_ITEMS)
    use_cache: bool = True


@router.post("/competitor")
async def analyze_competitor_route(req: CompetitorRequest) -> dict:
    """
    쿠팡 검색결과 URL 의 상위 N개 썸네일을 분석한다.
    robots.txt 차단 시 403, 네트워크 실패 시 502 로 정직하게 알린다.
    """
    url = req.url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="http(s) URL 을 입력하세요.")

    if req.use_cache:
        cached = get_cached(url)
        if cached is not None:
            cached = {**cached, "cached": True}
            return cached

    try:
        # 네트워크 + 이미지 분석은 블로킹 → 스레드풀에서
        result = await run_in_threadpool(
            analyze_competitor, url, req.max_items
        )
    except RobotsBlockedError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except httpx.HTTPStatusError as e:
        code = e.response.status_code if e.response is not None else "?"
        raise HTTPException(
            status_code=502,
            detail=f"대상 사이트 응답 오류({code}). 차단되었거나 페이지를 가져올 수 없습니다.",
        )
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=502, detail=f"대상 사이트 접속 실패: {e}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"분석 실패: {e}")

    if result.get("analyzed_count", 0) == 0:
        # 정적 HTML 에서 썸네일을 못 찾음(쿠팡 봇 차단/JS 렌더 가능성) — 정직하게 표시
        result["warning"] = (
            "썸네일을 추출하지 못했습니다. 대상이 봇을 차단했거나 "
            "정적 HTML 로는 상품 이미지를 얻을 수 없는 페이지일 수 있습니다."
        )

    if req.use_cache and result.get("analyzed_count", 0) > 0:
        set_cached(url, result)

    result["cached"] = False
    return result
