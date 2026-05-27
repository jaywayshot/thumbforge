"""브랜드 프리셋 라우트"""
from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.services.brand_store import (
    BrandPreset,
    create_brand,
    delete_brand,
    get_brand,
    list_brands,
    save_brand_asset,
    update_brand,
)

router = APIRouter(prefix="/api/brands", tags=["brands"])


class BrandCreate(BaseModel):
    name: str


class BrandUpdate(BaseModel):
    name: Optional[str] = None
    accent_color: Optional[str] = None
    sub_color: Optional[str] = None
    text_color: Optional[str] = None
    default_headline: Optional[str] = None
    default_sub_text: Optional[str] = None
    default_badge: Optional[str] = None
    tone_keywords: Optional[list[str]] = None
    forbidden_words: Optional[list[str]] = None


@router.get("", response_model=list[BrandPreset])
async def api_list_brands():
    return list_brands()


@router.post("", response_model=BrandPreset)
async def api_create_brand(body: BrandCreate):
    return create_brand(body.name)


@router.get("/{brand_id}", response_model=BrandPreset)
async def api_get_brand(brand_id: str):
    b = get_brand(brand_id)
    if not b:
        raise HTTPException(status_code=404, detail="브랜드 없음")
    return b


@router.patch("/{brand_id}", response_model=BrandPreset)
async def api_update_brand(brand_id: str, body: BrandUpdate):
    b = update_brand(brand_id, **body.model_dump(exclude_unset=True))
    if not b:
        raise HTTPException(status_code=404, detail="브랜드 없음")
    return b


@router.delete("/{brand_id}")
async def api_delete_brand(brand_id: str):
    ok = delete_brand(brand_id)
    if not ok:
        raise HTTPException(status_code=404, detail="브랜드 없음")
    return {"ok": True}


@router.post("/{brand_id}/logo")
async def api_upload_logo(brand_id: str, file: UploadFile = File(...)):
    if not get_brand(brand_id):
        raise HTTPException(status_code=404, detail="브랜드 없음")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="로고는 5MB 이하")
    if not file.filename:
        raise HTTPException(status_code=400, detail="파일명 없음")
    filename = save_brand_asset(brand_id, "logo", data, file.filename)
    return {"ok": True, "filename": filename}


@router.post("/{brand_id}/font")
async def api_upload_font(brand_id: str, file: UploadFile = File(...)):
    if not get_brand(brand_id):
        raise HTTPException(status_code=404, detail="브랜드 없음")
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="폰트는 20MB 이하")
    if not file.filename or not file.filename.lower().endswith((".ttf", ".otf", ".ttc")):
        raise HTTPException(status_code=400, detail=".ttf/.otf/.ttc 만 허용")
    filename = save_brand_asset(brand_id, "font", data, file.filename)
    return {"ok": True, "filename": filename}
