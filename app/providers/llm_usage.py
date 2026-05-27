"""
LLM 사용량 추적

호출마다 토큰 수·예상 비용을 logging.info 로 남기고,
workspace/temp/llm_usage.jsonl 에 한 줄씩 추가(append)한다.
GET /api/llm/usage 가 이 파일을 읽어 누적 통계를 만든다.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Dict, Optional

from app.settings import settings

logger = logging.getLogger("thumbforge")


def _default_path() -> Path:
    return settings.temp_path / "llm_usage.jsonl"


def record(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    *,
    cost_usd: float = 0.0,
    regenerated: bool = False,
    cached: bool = False,
    usage_path: Optional[Path] = None,
) -> None:
    path = usage_path or _default_path()
    entry = {
        "ts": time.time(),
        "provider": provider,
        "model": model,
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "cost_usd": round(float(cost_usd or 0.0), 8),
        "regenerated": bool(regenerated),
        "cached": bool(cached),
    }
    logger.info(
        "[llm-usage] %s/%s tokens=%d+%d cost=$%.6f%s%s",
        provider, model, entry["prompt_tokens"], entry["completion_tokens"],
        entry["cost_usd"],
        " (regen)" if regenerated else "",
        " (cache)" if cached else "",
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("[llm-usage] 기록 실패: %s", e)


def read_stats(usage_path: Optional[Path] = None) -> Dict:
    """누적 통계 집계 (GET /api/llm/usage 용)."""
    path = usage_path or _default_path()
    total = {
        "total_calls": 0,
        "live_calls": 0,
        "cached_calls": 0,
        "regenerated_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cost_usd": 0.0,
        "by_model": {},
    }
    if not path.exists():
        return total
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                total["total_calls"] += 1
                if e.get("cached"):
                    total["cached_calls"] += 1
                else:
                    total["live_calls"] += 1
                if e.get("regenerated"):
                    total["regenerated_calls"] += 1
                total["prompt_tokens"] += int(e.get("prompt_tokens", 0))
                total["completion_tokens"] += int(e.get("completion_tokens", 0))
                total["cost_usd"] += float(e.get("cost_usd", 0.0))

                m = e.get("model", "?")
                bm = total["by_model"].setdefault(
                    m, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0}
                )
                bm["calls"] += 1
                bm["prompt_tokens"] += int(e.get("prompt_tokens", 0))
                bm["completion_tokens"] += int(e.get("completion_tokens", 0))
                bm["cost_usd"] += float(e.get("cost_usd", 0.0))
    except Exception as e:
        logger.warning("[llm-usage] 통계 읽기 실패: %s", e)

    total["cost_usd"] = round(total["cost_usd"], 6)
    for bm in total["by_model"].values():
        bm["cost_usd"] = round(bm["cost_usd"], 6)
    return total
