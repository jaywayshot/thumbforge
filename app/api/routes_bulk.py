"""대량(Bulk) 처리 라우트"""
from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.jobs.bulk_worker import run_bulk_job
from app.jobs.registry import registry, run_in_background
from app.settings import settings

router = APIRouter(prefix="/api/bulk", tags=["bulk"])


@router.post("/upload")
async def bulk_upload(
    file: UploadFile = File(...),
    concept: str = Form("white_minimal"),
    platform: str = Form("coupang"),
    variants_per_image: int = Form(4),
    text_json: str = Form("{}"),
    category_hint: str = Form(""),
):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail=".zip 파일만 허용됩니다")

    contents = await file.read()
    if len(contents) > settings.max_upload_mb * 1024 * 1024 * 10:  # 대량은 10배 허용
        raise HTTPException(status_code=413, detail="파일이 너무 큽니다")

    try:
        text = json.loads(text_json) if text_json else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="text_json 파싱 실패")

    job = registry.create(
        kind="bulk_generate",
        meta={"concept": concept, "platform": platform, "variants_per_image": variants_per_image},
    )

    run_in_background(
        run_bulk_job,
        job_id=job.job_id,
        zip_bytes=contents,
        concept=concept,
        platform=platform,
        variants_per_image=variants_per_image,
        text=text,
        category_hint=category_hint or None,
    )

    return {"job_id": job.job_id, "status": "pending", "poll_url": f"/api/bulk/status/{job.job_id}"}


@router.get("/status/{job_id}")
async def bulk_status(job_id: str):
    rec = registry.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="job 없음")
    return rec.to_dict()


@router.get("/recent")
async def bulk_recent(limit: int = 20):
    return [r.to_dict() for r in registry.list_recent(limit)]


@router.get("/result/{job_id}.zip")
async def bulk_result(job_id: str):
    if "/" in job_id or ".." in job_id:
        raise HTTPException(status_code=400, detail="잘못된 경로")
    path = settings.outputs_path / "bulk" / f"{job_id}.zip"
    if not path.exists():
        raise HTTPException(status_code=404, detail="결과 ZIP 없음 (아직 생성 중일 수 있음)")
    return FileResponse(path, media_type="application/zip", filename=f"thumbnails_{job_id}.zip")
