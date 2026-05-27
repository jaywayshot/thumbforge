"""사용자 피드백 라우트 (variant 선호 데이터 축적)"""
from __future__ import annotations

import csv
import io
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app.services import feedback_store, job_store
from app.services.feedback_store import VALID_TYPES, FeedbackEntry

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class FeedbackRequest(BaseModel):
    variant_id: str               # 전역 variant ID (<job_id>_v1)
    feedback_type: str            # winner | loser | discard
    user_note: Optional[str] = None


@router.post("")
async def post_feedback(req: FeedbackRequest) -> dict:
    """
    variant 에 대한 사용자 의견 기록. variant_id 로 generation 메타를 자동 복원한다.
    같은 variant 의 의견은 새 줄로 추가되며, 조회 시 가장 최근 것이 유효(마지막 의견이 진실).
    """
    if req.feedback_type not in VALID_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"feedback_type 은 {VALID_TYPES} 중 하나여야 합니다.",
        )

    meta = job_store.get_variant_meta(req.variant_id)
    if meta is None:
        raise HTTPException(
            status_code=404,
            detail="해당 variant 의 generation 메타데이터를 찾을 수 없습니다.",
        )

    entry = FeedbackEntry(
        feedback_type=req.feedback_type,
        user_note=req.user_note,
        **meta,
    )
    feedback_store.record_feedback(entry)
    return {"feedback_id": entry.feedback_id, "recorded_at": entry.created_at}


@router.get("/recent")
async def recent_feedback(limit: int = 50) -> dict:
    limit = max(1, min(int(limit), 500))
    return {"items": feedback_store.list_feedback(limit=limit)}


@router.get("/stats")
async def feedback_stats() -> dict:
    return feedback_store.aggregate_stats()


@router.get("/export.csv")
async def export_csv() -> Response:
    """전체 피드백(현재 상태)을 CSV 로 내보낸다. 표준 csv 모듈만 사용."""
    rows = feedback_store.list_feedback(limit=10_000_000)
    fields = list(FeedbackEntry.model_fields.keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({k: r.get(k, "") for k in fields})
    csv_bytes = buf.getvalue().encode("utf-8-sig")  # 엑셀 한글 호환 BOM
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="feedback_export.csv"'},
    )
