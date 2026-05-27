"""업로드 라우트"""
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.models.schemas import UploadResponse
from app.services.concept_loader import (
    detect_category_by_filename,
    suggest_concepts_for_category,
)
from app.services.storage import save_upload, open_image
from app.settings import settings

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)) -> UploadResponse:
    contents = await file.read()
    if len(contents) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"파일이 너무 큽니다 (최대 {settings.max_upload_mb}MB)")

    if not file.filename:
        raise HTTPException(status_code=400, detail="파일명이 없습니다")

    upload_id, path = save_upload(contents, file.filename)
    img = open_image(path)

    # 알파 채널 여부
    has_alpha = False
    try:
        import numpy as np
        a = np.array(img.split()[-1])
        has_alpha = float((a < 10).mean()) > 0.01
    except Exception:
        pass

    # 품질 경고
    warnings: list[str] = []
    if min(img.size) < 600:
        warnings.append("해상도가 낮습니다 (최소 600px 권장)")
    if max(img.size) > 4000:
        warnings.append("해상도가 너무 큽니다, 처리 시간이 길어질 수 있습니다")

    category = detect_category_by_filename(file.filename)
    suggestions = suggest_concepts_for_category(category)

    return UploadResponse(
        upload_id=upload_id,
        filename=file.filename,
        width=img.width,
        height=img.height,
        has_alpha=has_alpha,
        detected_category=category,
        suggested_concepts=suggestions,
        quality_warnings=warnings,
    )
