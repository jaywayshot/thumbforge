"""
YAML 설정 로더
하드코딩 금지 원칙에 따라 모든 프리셋은 YAML에서 읽음
"""
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

import yaml

from app.settings import CONFIG_DIR


def _load_yaml(filename: str) -> Dict[str, Any]:
    path = CONFIG_DIR / filename
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=1)
def get_concepts() -> Dict[str, Dict[str, Any]]:
    return _load_yaml("concepts.yaml").get("concepts", {})


@lru_cache(maxsize=1)
def get_platforms() -> Dict[str, Dict[str, Any]]:
    return _load_yaml("platforms.yaml").get("platforms", {})


@lru_cache(maxsize=1)
def get_categories() -> Dict[str, Dict[str, Any]]:
    return _load_yaml("categories.yaml").get("categories", {})


# ───────── 헬퍼 ─────────

def get_concept(name: str) -> Dict[str, Any]:
    concepts = get_concepts()
    if name not in concepts:
        # fallback: 첫 번째 컨셉
        first = next(iter(concepts.values()))
        return first
    return concepts[name]


def get_platform(name: str) -> Dict[str, Any]:
    platforms = get_platforms()
    if name not in platforms:
        return platforms.get("coupang", {})
    return platforms[name]


def list_concept_names() -> List[str]:
    return list(get_concepts().keys())


def list_platform_names() -> List[str]:
    return list(get_platforms().keys())


def detect_category_by_filename(filename: str) -> str:
    """파일명으로 카테고리 추정 (간단 휴리스틱)"""
    name_lower = filename.lower()
    for cat_key, cat in get_categories().items():
        for kw in cat.get("keywords", []):
            if kw.lower() in name_lower:
                return cat_key
    return "general"


def suggest_concepts_for_category(category: str) -> List[str]:
    cats = get_categories()
    cat = cats.get(category) or cats.get("general", {})
    return cat.get("recommended_concepts", [])


# ───────── 금지문구 검사 ─────────

def check_forbidden_words(text: str, platform: str) -> List[str]:
    """플랫폼 금지문구 포함 여부 → 걸린 단어 리스트 반환"""
    if not text:
        return []
    p = get_platform(platform)
    hits = []
    for word in p.get("forbidden_words", []):
        if word in text:
            hits.append(word)
    return hits


def check_warning_words(text: str, platform: str) -> List[str]:
    if not text:
        return []
    p = get_platform(platform)
    return [w for w in p.get("text_warning_words", []) if w in text]
