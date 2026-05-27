"""
생성된 배경(scene) 이미지 캐시 — 동일 조합 재생성 시 API 재호출 방지(비용 절약)

키: (product_info.cache_signature, concept_id, platform) 해시
저장: workspace/temp/scene_cache/<key>.png + scene_cache.json(인덱스, TTL 24h)
fresh=True 면 캐시를 읽지 않는다(쓰기는 함).
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Optional

from PIL import Image

from app.settings import settings

TTL_SECONDS = 24 * 60 * 60


def _dir() -> Path:
    p = settings.temp_path / "scene_cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _index_path() -> Path:
    return _dir() / "scene_cache.json"


def make_key(sig: str, concept_id: str, platform: str) -> str:
    raw = f"{sig}|{concept_id}|{platform}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _load_index() -> dict:
    p = _index_path()
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save_index(idx: dict) -> None:
    tmp = _index_path().with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)
    tmp.replace(_index_path())


def get(key: str, *, now: Optional[float] = None) -> Optional[Image.Image]:
    now = time.time() if now is None else now
    entry = _load_index().get(key)
    if not entry:
        return None
    if now - entry.get("ts", 0) > TTL_SECONDS:
        return None
    img_path = _dir() / f"{key}.png"
    if not img_path.exists():
        return None
    try:
        return Image.open(img_path).convert("RGB")
    except Exception:
        return None


def set(key: str, image: Image.Image, *, now: Optional[float] = None) -> None:
    now = time.time() if now is None else now
    img_path = _dir() / f"{key}.png"
    try:
        image.convert("RGB").save(img_path, "PNG")
    except Exception:
        return
    idx = _load_index()
    idx[key] = {"ts": now}
    _save_index(idx)
