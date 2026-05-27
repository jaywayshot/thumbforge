"""레퍼런스 이미지 업로드/분석 라우트 (스타일 가이드)"""
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.services import reference_store

router = APIRouter(prefix="/api/reference", tags=["reference"])


@router.post("/upload")
async def upload_reference(file: UploadFile = File(...)) -> dict:
    """
    레퍼런스 이미지 업로드 → 로컬 분석(색/톤/무드). 외부 전송 없음.
    반환된 reference_id 를 generate 요청에 넣으면 신 프롬프트에 반영된다.
    """
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="레퍼런스 이미지는 10MB 이하")
    try:
        analysis = reference_store.analyze_bytes(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"이미지 분석 실패: {e}")
    ref_id = reference_store.save_reference(analysis)
    return {"reference_id": ref_id, **analysis}
