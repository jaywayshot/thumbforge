"""
경쟁사 분석 결과 캐시 (URL 해시 키, 24시간 TTL)

같은 URL 재요청 시 네트워크 부담을 줄이기 위한 파일 캐시.
workspace/temp/competitor_cache.json 한 파일에 모아 저장한다.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Dict, Optional

from app.settings import settings

TTL_SECONDS = 24 * 60 * 60  # 24시간


def _default_cache_path() -> Path:
    return settings.temp_path / "competitor_cache.json"


def url_key(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()


def _load_all(path: Path) -> Dict:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        # 손상된 캐시는 무시(다음 저장 때 덮어씀)
        return {}


def get_cached(
    url: str,
    *,
    cache_path: Optional[Path] = None,
    now: Optional[float] = None,
) -> Optional[Dict]:
    """TTL 내 캐시가 있으면 결과 dict, 없으면 None."""
    path = cache_path or _default_cache_path()
    now = time.time() if now is None else now
    entry = _load_all(path).get(url_key(url))
    if not entry:
        return None
    if now - entry.get("ts", 0) > TTL_SECONDS:
        return None
    return entry.get("result")


def set_cached(
    url: str,
    result: Dict,
    *,
    cache_path: Optional[Path] = None,
    now: Optional[float] = None,
) -> None:
    path = cache_path or _default_cache_path()
    now = time.time() if now is None else now
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _load_all(path)
    data[url_key(url)] = {"ts": now, "url": url, "result": result}
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)
