"""생성 라우트"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.core.pipeline import run_generation
from app.models.schemas import GenerateRequest, GenerateResponse
from app.services.concept_loader import (
    list_concept_names,
    list_platform_names,
    get_concepts,
    get_platforms,
    get_categories,
    get_categories_v2,
)

router = APIRouter(prefix="/api", tags=["generate"])


@router.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest) -> GenerateResponse:
    try:
        # 합성은 CPU 바운드라 스레드풀에서
        result = await run_in_threadpool(run_generation, req)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"생성 실패: {e}")


@router.get("/concepts")
async def list_concepts() -> dict:
    """프론트엔드 UI 표시용 - 컨셉 라벨/설명까지"""
    return {
        k: {"label": v.get("label", k), "description": v.get("description", "")}
        for k, v in get_concepts().items()
    }


@router.get("/platforms")
async def list_platforms() -> dict:
    return {
        k: {"label": v.get("label", k), "sizes": v.get("sizes", {})}
        for k, v in get_platforms().items()
    }


@router.get("/categories/v2")
async def list_categories_v2() -> dict:
    """라이프스타일 신 생성용 카테고리 마스터 (UI 제품정보 입력용)."""
    return get_categories_v2()


@router.get("/categories")
async def list_categories() -> dict:
    """카테고리 → 라벨/추천 컨셉/기본 레이아웃 (UI 자동 추천용)"""
    return {
        k: {
            "label": v.get("label", k),
            "recommended_concepts": v.get("recommended_concepts", []),
            "default_layout": v.get("default_layout", "center_product"),
        }
        for k, v in get_categories().items()
    }
