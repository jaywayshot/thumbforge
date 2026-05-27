"""
FastAPI 메인 진입점
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
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

# 표준 logging 모듈만 사용. 자체 named 로거에 핸들러를 한 번만 붙여
# uvicorn/pytest 등 어떤 실행 환경에서도 startup 로그가 보이게 한다.
logger = logging.getLogger("thumbforge")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False  # 루트로 전파해 중복 출력되는 것 방지


def _validate_config_on_startup() -> None:
    """
    기동 시 설정(YAML) 무결성 점검 — fail-soft.
    ─ YAML 로드/파싱 실패: ERROR 로깅 후 기본값으로 계속 진행
    ─ 의미적 문제(잘못된 색상/레이아웃/참조, 금지어 충돌 등): WARNING 로깅
      해당 항목은 무시하고 서버는 정상 기동 (절대 죽이지 않음)
    """
    try:
        from app.services.config_validate import validate_config
        errors = validate_config()
    except Exception as e:  # YAML 파싱 실패 등 로드 단계 예외
        logger.error("설정 로드 실패(YAML 파싱 등): %s — 기본값으로 계속 진행합니다.", e)
        return

    if errors:
        logger.warning(
            "설정 검증 경고 %d건 — 문제 항목은 무시하고 기동합니다:", len(errors)
        )
        for msg in errors:
            logger.warning("  - %s", msg)
    else:
        logger.info("설정 무결성 검증 통과 — 모든 컨셉/플랫폼/카테고리 정상.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    _validate_config_on_startup()
    yield
    # shutdown (현재 정리할 리소스 없음)


app = FastAPI(
    title="ThumbForge - AI 쇼핑몰 썸네일 생성 SaaS",
    description="제품 이미지 → AI 자동 누끼 → 컨셉 배경 → 매출형 썸네일",
    version="0.1.0",
    lifespan=lifespan,
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
