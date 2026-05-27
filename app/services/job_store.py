"""
생성(generation) 메타데이터 영속화

기존엔 GenerateResponse 가 메모리에만 있었다. 피드백 기록 시 variant 메타데이터
(컨셉/레이아웃/문구/CTR 등)를 복원할 수 있도록 workspace/jobs/<job_id>.json 에 저장한다.

variant_id 는 job 내부에서 v1..vN 으로 반복되므로, 전역 유일 ID 는
<job_id>_<variant_id> 형태(예: ab12cd34ef56_v1)로 합성한다.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from app.settings import settings


def _path(job_id: str) -> Path:
    return settings.jobs_path / f"{job_id}.json"


def make_global_variant_id(job_id: str, variant_id: str) -> str:
    return f"{job_id}_{variant_id}"


def split_global_variant_id(global_id: str) -> tuple[str, str]:
    """<job_id>_<variant_id> → (job_id, variant_id). job_id 는 언더스코어 없는 hex."""
    job_id, _, variant_id = global_id.partition("_")
    return job_id, variant_id


def save_generation_meta(
    job_id: str,
    *,
    upload_id: str,
    category: str,
    concept: str,
    platform: str,
    text_provider: str,
    variants: Dict[str, dict],
) -> None:
    """variants: {variant_id: {layout_used, headline, sub_text, badge, has_discount, ctr_estimate}}"""
    settings.jobs_path.mkdir(parents=True, exist_ok=True)
    meta = {
        "job_id": job_id,
        "upload_id": upload_id,
        "category": category,
        "concept": concept,
        "platform": platform,
        "text_provider": text_provider,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "variants": variants,
    }
    tmp = _path(job_id).with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    tmp.replace(_path(job_id))


def load_job(job_id: str) -> Optional[dict]:
    p = _path(job_id)
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def get_variant_meta(global_variant_id: str) -> Optional[dict]:
    """전역 variant ID → 그 variant 의 메타데이터(+job 공통 필드 병합)."""
    job_id, variant_id = split_global_variant_id(global_variant_id)
    job = load_job(job_id)
    if not job:
        return None
    v = (job.get("variants") or {}).get(variant_id)
    if v is None:
        return None
    return {
        "job_id": job_id,
        "variant_id": global_variant_id,
        "upload_id": job.get("upload_id", ""),
        "category": job.get("category", "general"),
        "concept": job.get("concept", ""),
        "platform": job.get("platform", ""),
        "text_provider": job.get("text_provider", "mock"),
        "layout_used": v.get("layout_used", ""),
        "headline": v.get("headline"),
        "sub_text": v.get("sub_text"),
        "badge": v.get("badge"),
        "has_discount": bool(v.get("has_discount", False)),
        "ctr_estimate": int(v.get("ctr_estimate", 0)),
    }


def cleanup_old_jobs(days: int = 30) -> int:
    """days 일 이상 지난 job 메타 파일 삭제. 삭제 개수 반환."""
    cutoff = time.time() - days * 86400
    removed = 0
    if not settings.jobs_path.exists():
        return 0
    for p in settings.jobs_path.glob("*.json"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
                removed += 1
        except OSError:
            continue
    return removed
