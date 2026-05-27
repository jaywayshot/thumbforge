"""
오래된 generation 메타데이터 정리 (수동 실행)

workspace/jobs/<job_id>.json 중 N일(기본 30) 이상 지난 파일을 삭제한다.
피드백 데이터(workspace/feedback/)는 건드리지 않는다.

사용법:
  python scripts/cleanup_old_jobs.py            # 30일 이상 삭제
  python scripts/cleanup_old_jobs.py --days 7   # 7일 이상 삭제
  python scripts/cleanup_old_jobs.py --dry-run  # 삭제하지 않고 개수만 표시
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services import job_store
from app.settings import settings


def main() -> None:
    ap = argparse.ArgumentParser(description="오래된 job 메타 정리")
    ap.add_argument("--days", type=int, default=30, help="이 일수 이상 지난 파일 삭제(기본 30)")
    ap.add_argument("--dry-run", action="store_true", help="삭제하지 않고 대상 개수만 표시")
    args = ap.parse_args()

    if args.dry_run:
        cutoff = time.time() - args.days * 86400
        targets = [p for p in settings.jobs_path.glob("*.json")
                   if p.stat().st_mtime < cutoff]
        print(f"[dry-run] {args.days}일 이상 지난 job 메타 {len(targets)}건 (삭제 안 함)")
        return

    removed = job_store.cleanup_old_jobs(days=args.days)
    print(f"삭제 완료: {removed}건 ({args.days}일 이상)")


if __name__ == "__main__":
    main()
