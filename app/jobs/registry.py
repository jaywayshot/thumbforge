"""
인-메모리 작업 큐
── 추후 Celery + Redis 로 교체 시 같은 인터페이스 유지
── BackgroundTasks(스레드풀)에서 처리됨
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class JobRecord:
    job_id: str
    kind: str                            # "bulk_generate" 등
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0                # 0.0 ~ 1.0
    total: int = 0
    done: int = 0
    message: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0
    result: Optional[dict] = None
    error: Optional[str] = None
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "status": self.status.value,
            "progress": round(self.progress, 3),
            "total": self.total,
            "done": self.done,
            "message": self.message,
            "elapsed_sec": round(
                (self.finished_at or time.time()) - self.started_at, 2
            ) if self.started_at else 0,
            "result": self.result,
            "error": self.error,
            "meta": self.meta,
        }


class JobRegistry:
    """단일 프로세스용 인-메모리 레지스트리 (스레드 안전)"""

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()

    def create(self, kind: str, total: int = 0, meta: Optional[dict] = None) -> JobRecord:
        job_id = uuid.uuid4().hex[:12]
        rec = JobRecord(
            job_id=job_id,
            kind=kind,
            total=total,
            meta=meta or {},
            started_at=time.time(),
        )
        with self._lock:
            self._jobs[job_id] = rec
        return rec

    def get(self, job_id: str) -> Optional[JobRecord]:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs) -> None:
        with self._lock:
            rec = self._jobs.get(job_id)
            if not rec:
                return
            for k, v in kwargs.items():
                if hasattr(rec, k):
                    setattr(rec, k, v)

    def tick(self, job_id: str, message: str = "") -> None:
        """진행 단위 1 증가"""
        with self._lock:
            rec = self._jobs.get(job_id)
            if not rec:
                return
            rec.done += 1
            if rec.total > 0:
                rec.progress = rec.done / rec.total
            if message:
                rec.message = message

    def finish(self, job_id: str, result: Optional[dict] = None) -> None:
        with self._lock:
            rec = self._jobs.get(job_id)
            if not rec:
                return
            rec.status = JobStatus.SUCCESS
            rec.progress = 1.0
            rec.result = result
            rec.finished_at = time.time()
            rec.message = "완료"

    def fail(self, job_id: str, error: str) -> None:
        with self._lock:
            rec = self._jobs.get(job_id)
            if not rec:
                return
            rec.status = JobStatus.FAILED
            rec.error = error
            rec.finished_at = time.time()

    def list_recent(self, limit: int = 20) -> list[JobRecord]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda r: r.started_at, reverse=True)
            return jobs[:limit]


# 전역 싱글톤
registry = JobRegistry()


def run_in_background(target: Callable, *args, **kwargs) -> None:
    """간단한 데몬 스레드로 백그라운드 실행"""
    t = threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True)
    t.start()
