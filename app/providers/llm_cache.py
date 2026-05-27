"""
LLM 문구 추천 결과 캐시

키: (provider, model, category, concept, platform) 해시
  └ 스펙의 (category, concept, platform) 에 provider/model 을 더해
    provider 전환 시 다른 provider 의 캐시가 잘못 반환되는 버그를 막는다.
저장: workspace/temp/llm_cache.json (TTL 24시간)
용량: 파일이 1MB 를 넘으면 오래된(ts 오름차순) 항목부터 삭제.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Dict, Optional

from app.settings import settings

TTL_SECONDS = 24 * 60 * 60
MAX_BYTES = 1024 * 1024  # 1MB


def _default_path() -> Path:
    return settings.temp_path / "llm_cache.json"


def make_key(provider: str, model: str, category: str, concept: str,
             platform: Optional[str]) -> str:
    raw = f"{provider}|{model}|{category}|{concept}|{platform or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load(path: Path) -> Dict:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def get(provider: str, model: str, category: str, concept: str,
        platform: Optional[str], *, cache_path: Optional[Path] = None,
        now: Optional[float] = None) -> Optional[Dict]:
    path = cache_path or _default_path()
    now = time.time() if now is None else now
    entry = _load(path).get(make_key(provider, model, category, concept, platform))
    if not entry:
        return None
    if now - entry.get("ts", 0) > TTL_SECONDS:
        return None
    return entry.get("result")


def set(provider: str, model: str, category: str, concept: str,
        platform: Optional[str], result: Dict, *,
        cache_path: Optional[Path] = None, now: Optional[float] = None) -> None:
    path = cache_path or _default_path()
    now = time.time() if now is None else now
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _load(path)
    data[make_key(provider, model, category, concept, platform)] = {
        "ts": now,
        "meta": {"provider": provider, "model": model, "category": category,
                 "concept": concept, "platform": platform},
        "result": result,
    }
    data = _evict_if_needed(data)
    _atomic_write(path, data)


def _evict_if_needed(data: Dict) -> Dict:
    """직렬화 크기가 1MB 를 넘으면 오래된 항목부터 제거."""
    def size(d: Dict) -> int:
        return len(json.dumps(d, ensure_ascii=False).encode("utf-8"))

    if size(data) <= MAX_BYTES:
        return data
    # ts 오름차순(오래된 것 먼저)으로 정렬해 하나씩 제거
    items = sorted(data.items(), key=lambda kv: kv[1].get("ts", 0))
    while items and size(dict(items)) > MAX_BYTES:
        items.pop(0)
    return dict(items)


def _atomic_write(path: Path, data: Dict) -> None:
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)
