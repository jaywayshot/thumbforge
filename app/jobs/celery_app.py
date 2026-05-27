"""
Celery 전환 준비 (USE_CELERY=true 일 때만 활성화)

설계 원칙
─ 기본은 registry.run_in_background(스레드풀) → 기존 동작 100% 그대로
─ USE_CELERY=true + celery 설치 + redis 가동 시에만 Celery 워커로 처리
─ app/jobs/registry.py 인터페이스는 손대지 않음
   (Celery 워커도 동일한 JobRegistry 를 갱신하는 구조를 유지)

celery 는 선택적 의존성이다. requirements.txt 기본에는 없고,
docker-compose 의 worker 컨테이너에서만 설치한다.
따라서 미설치 환경에서도 이 모듈 import 는 절대 실패하지 않는다.
"""
from __future__ import annotations

import base64
import os
from typing import Optional

# celery 선택적 import (미설치여도 import 시점에 죽지 않음)
try:
    from celery import Celery  # type: ignore
    _CELERY_AVAILABLE = True
except Exception:  # pragma: no cover - celery 미설치 환경
    Celery = None  # type: ignore
    _CELERY_AVAILABLE = False


def _broker_url() -> str:
    # settings.redis_url → 환경변수 순으로 폴백
    try:
        from app.settings import settings
        base = getattr(settings, "redis_url", None) or "redis://localhost:6379/0"
    except Exception:
        base = "redis://localhost:6379/0"
    return os.getenv("CELERY_BROKER_URL", base)


celery_app = None
if _CELERY_AVAILABLE:
    celery_app = Celery(
        "thumbforge",
        broker=_broker_url(),
        backend=os.getenv("CELERY_RESULT_BACKEND", _broker_url()),
    )
    celery_app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_track_started=True,
        worker_max_tasks_per_child=50,
    )

    @celery_app.task(name="thumbforge.run_bulk_job")
    def run_bulk_job_task(
        job_id: str,
        zip_b64: str,
        concept: str,
        platform: str,
        variants_per_image: int,
        text: Optional[dict] = None,
        category_hint: Optional[str] = None,
    ) -> None:
        """Celery 태스크 래퍼. zip 바이트는 JSON 직렬화를 위해 base64 로 받는다."""
        from app.jobs.bulk_worker import run_bulk_job
        zip_bytes = base64.b64decode(zip_b64)
        run_bulk_job(
            job_id=job_id,
            zip_bytes=zip_bytes,
            concept=concept,
            platform=platform,
            variants_per_image=variants_per_image,
            text=text,
            category_hint=category_hint,
        )


def use_celery() -> bool:
    """현재 설정상 Celery 경로를 써야 하는지."""
    try:
        from app.settings import settings
        flag = bool(getattr(settings, "use_celery", False))
    except Exception:
        flag = os.getenv("USE_CELERY", "").lower() in ("1", "true", "yes", "on")
    return flag and _CELERY_AVAILABLE and celery_app is not None


def dispatch_bulk_job(
    *,
    job_id: str,
    zip_bytes: bytes,
    concept: str,
    platform: str,
    variants_per_image: int,
    text: Optional[dict] = None,
    category_hint: Optional[str] = None,
) -> str:
    """
    대량 작업을 디스패치한다.
    USE_CELERY 면 Celery 큐로, 아니면 기존 스레드풀로.
    실제 사용한 방식을 문자열("celery" | "thread")로 반환.
    """
    if use_celery():
        zip_b64 = base64.b64encode(zip_bytes).decode("ascii")
        run_bulk_job_task.delay(
            job_id,
            zip_b64,
            concept,
            platform,
            variants_per_image,
            text,
            category_hint,
        )
        return "celery"

    # 기본 경로: 기존 스레드풀 동작 그대로 (registry 인터페이스 유지)
    from app.jobs.bulk_worker import run_bulk_job
    from app.jobs.registry import run_in_background
    run_in_background(
        run_bulk_job,
        job_id=job_id,
        zip_bytes=zip_bytes,
        concept=concept,
        platform=platform,
        variants_per_image=variants_per_image,
        text=text,
        category_hint=category_hint,
    )
    return "thread"
