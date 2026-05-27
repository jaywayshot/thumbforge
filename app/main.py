"""
FastAPI 메인 진입점
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_brand import router as brand_router
from app.api.routes_bulk import router as bulk_router
from app.api.routes_download import router as download_router
from app.api.routes_generate import router as generate_router
from app.api.routes_upload import router as upload_router
from app.settings import settings

app = FastAPI(
    title="ThumbForge - AI 쇼핑몰 썸네일 생성 SaaS",
    description="제품 이미지 → AI 자동 누끼 → 컨셉 배경 → 매출형 썸네일",
    version="0.1.0",
)

# CORS (로컬 개발 + 향후 SPA 분리 대비)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우트
app.include_router(upload_router)
app.include_router(generate_router)
app.include_router(bulk_router)
app.include_router(brand_router)
app.include_router(download_router)

# 정적 페이지 (간단한 데모 UI)
STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def root():
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"message": "ThumbForge API. GET /docs 로 API 문서 확인"}


@app.get("/healthz")
async def healthz():
    return {
        "ok": True,
        "bg_provider": settings.bg_provider,
        "matting_model": settings.matting_model,
    }
