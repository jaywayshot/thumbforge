"""파일 다운로드 라우트"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.settings import settings

router = APIRouter(tags=["download"])


@router.get("/files/{job_id}/{filename}")
async def get_file(job_id: str, filename: str):
    # 경로 traversal 방어
    if ".." in job_id or "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="잘못된 경로")
    # bulk/<id>.zip 처리
    if job_id == "bulk":
        path = settings.outputs_path / "bulk" / filename
        media = "application/zip"
    else:
        if "/" in job_id:
            raise HTTPException(status_code=400, detail="잘못된 경로")
        path = settings.outputs_path / job_id / filename
        media = "image/png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    return FileResponse(path, media_type=media, filename=filename)
