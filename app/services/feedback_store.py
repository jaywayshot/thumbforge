"""
사용자 피드백 저장소 (variant 선호 데이터 축적)

저장 방식
─ workspace/feedback/feedback.jsonl 에 한 줄 = 한 피드백 (append-only)
─ 1MB 초과 시 회전: feedback.jsonl → feedback-001.jsonl (rename, 원자적) 후 새 파일
─ 동시 쓰기 안전: 프로세스 내 threading.Lock 으로 직렬화
  (기본 단일 uvicorn 프로세스 + 스레드풀 기준. 멀티 프로세스면 외부 큐 권장)

"덮어쓰기" 정책
─ 파일은 append-only(데이터 손실 금지). 같은 variant_id 의 의견이 바뀌면
  새 줄을 추가하고, 읽을 때 variant_id 별 "가장 최근" 항목만 유효로 본다.
  → 5단계 UX("마지막 의견이 진실") + append-only 무손실을 동시에 만족.

외부 전송 없음. 데이터는 workspace/feedback/ 에만 머문다.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.settings import settings

MAX_BYTES = 1024 * 1024  # 1MB 회전 임계치
VALID_TYPES = ("winner", "loser", "discard")

_write_lock = threading.Lock()


# ───────── 데이터 모델 ─────────

class FeedbackEntry(BaseModel):
    feedback_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    job_id: str
    variant_id: str               # 전역 유일 ID (예: <job_id>_v1)
    upload_id: str = ""
    category: str = "general"
    concept: str = ""
    platform: str = ""
    layout_used: str = ""
    headline: Optional[str] = None
    sub_text: Optional[str] = None
    badge: Optional[str] = None
    has_discount: bool = False
    ctr_estimate: int = 0
    text_provider: str = "mock"
    feedback_type: str = "winner"  # winner | loser | discard
    user_note: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ───────── 파일 경로 ─────────

def _dir() -> Path:
    p = settings.feedback_path
    p.mkdir(parents=True, exist_ok=True)
    return p


def _current_file() -> Path:
    return _dir() / "feedback.jsonl"


def _all_files() -> List[Path]:
    """회전된 파일(오래된 것 먼저) + 현재 파일."""
    d = _dir()
    rotated = sorted(d.glob("feedback-*.jsonl"))
    files = rotated[:]
    cur = _current_file()
    if cur.exists():
        files.append(cur)
    return files


def _next_rotated_path() -> Path:
    d = _dir()
    existing = sorted(d.glob("feedback-*.jsonl"))
    nums = []
    for f in existing:
        try:
            nums.append(int(f.stem.split("-")[1]))
        except (IndexError, ValueError):
            pass
    nxt = (max(nums) + 1) if nums else 1
    return d / f"feedback-{nxt:03d}.jsonl"


def _rotate_if_needed() -> None:
    """현재 파일이 1MB 이상이면 feedback-NNN.jsonl 로 rename(원자적)."""
    cur = _current_file()
    if cur.exists() and cur.stat().st_size >= MAX_BYTES:
        cur.rename(_next_rotated_path())  # rename 후 다음 append 가 새 파일 생성


# ───────── 기록 ─────────

def record_feedback(entry: FeedbackEntry) -> FeedbackEntry:
    line = json.dumps(entry.model_dump(), ensure_ascii=False)
    with _write_lock:
        _rotate_if_needed()
        with open(_current_file(), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    return entry


# ───────── 읽기 ─────────

def _read_all() -> List[dict]:
    out: List[dict] = []
    for fp in _all_files():
        try:
            with open(fp, "r", encoding="utf-8") as f:
                for raw in f:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        out.append(json.loads(raw))
                    except Exception:
                        continue
        except FileNotFoundError:
            continue
    return out


def _latest_per_variant(entries: List[dict]) -> List[dict]:
    """variant_id 별 가장 최근(created_at) 항목만 — '마지막 의견이 진실'."""
    by_variant: Dict[str, dict] = {}
    for e in entries:
        vid = e.get("variant_id")
        if not vid:
            continue
        prev = by_variant.get(vid)
        if prev is None or str(e.get("created_at", "")) >= str(prev.get("created_at", "")):
            by_variant[vid] = e
    return list(by_variant.values())


def list_feedback(limit: int = 100, **filters) -> List[dict]:
    """variant_id 별 최신 의견을, 필터 적용 후 created_at 내림차순으로 반환."""
    entries = _latest_per_variant(_read_all())
    if filters:
        def ok(e: dict) -> bool:
            return all(e.get(k) == v for k, v in filters.items())
        entries = [e for e in entries if ok(e)]
    entries.sort(key=lambda e: str(e.get("created_at", "")), reverse=True)
    return entries[: max(0, limit)]


# ───────── 집계 ─────────

def _winner_rate(group: List[dict]) -> dict:
    winners = sum(1 for e in group if e.get("feedback_type") == "winner")
    losers = sum(1 for e in group if e.get("feedback_type") == "loser")
    discards = sum(1 for e in group if e.get("feedback_type") == "discard")
    denom = winners + losers  # discard 는 winner rate 분모에서 제외
    rate = round(winners / denom, 4) if denom else None
    return {"winner": winners, "loser": losers, "discard": discards,
            "total": len(group), "winner_rate": rate}


def _group_rates(entries: List[dict], key: str) -> Dict[str, dict]:
    groups: Dict[str, List[dict]] = {}
    for e in entries:
        groups.setdefault(str(e.get(key, "")), []).append(e)
    return {k: _winner_rate(v) for k, v in sorted(groups.items())}


def _pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    """CTR 추정 점수 ↔ winner(1)/loser(0) 상관. 표본<2 또는 분산 0이면 None."""
    if len(xs) < 2:
        return None
    import numpy as np
    a = np.asarray(xs, dtype=float)
    b = np.asarray(ys, dtype=float)
    if a.std() == 0 or b.std() == 0:
        return None
    return round(float(np.corrcoef(a, b)[0, 1]), 4)


def aggregate_stats() -> dict:
    entries = _latest_per_variant(_read_all())
    overall = _winner_rate(entries)

    # 할인 뱃지 유무별
    with_discount = [e for e in entries if e.get("has_discount")]
    without_discount = [e for e in entries if not e.get("has_discount")]

    # CTR 추정 vs winner 선택 상관 (winner/loser 만)
    wl = [e for e in entries if e.get("feedback_type") in ("winner", "loser")]
    xs = [float(e.get("ctr_estimate", 0)) for e in wl]
    ys = [1.0 if e.get("feedback_type") == "winner" else 0.0 for e in wl]

    return {
        "total_feedback": len(entries),
        "summary": overall,
        "by_concept": _group_rates(entries, "concept"),
        "by_layout": _group_rates(entries, "layout_used"),
        "by_provider": _group_rates(entries, "text_provider"),
        "discount": {
            "with_discount": _winner_rate(with_discount),
            "without_discount": _winner_rate(without_discount),
        },
        "ctr_vs_winner_pearson": _pearson(xs, ys),
        "ctr_corr_sample_size": len(wl),
    }
