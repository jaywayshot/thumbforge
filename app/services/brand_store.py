"""
브랜드 프리셋 관리
─ JSON 파일 기반 (DB 도입 전 단순 영속화)
─ 브랜드별 로고/컬러/폰트/기본 헤드라인/금지문구 저장
─ 생성 시 컨셉 위에 덮어쓰기 (overlay) 방식
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from app.settings import settings, BASE_DIR


BRANDS_FILE = BASE_DIR / "workspace" / "brands.json"


class BrandPreset(BaseModel):
    brand_id: str
    name: str
    accent_color: Optional[str] = None        # 컨셉의 accent_color 덮어쓰기
    sub_color: Optional[str] = None
    text_color: Optional[str] = None
    logo_filename: Optional[str] = None       # workspace/brands/<id>/logo.png
    font_filename: Optional[str] = None       # 같은 폴더의 .ttf
    default_headline: Optional[str] = None
    default_sub_text: Optional[str] = None
    default_badge: Optional[str] = None
    tone_keywords: list[str] = Field(default_factory=list)  # AI 문구 추천 hint
    forbidden_words: list[str] = Field(default_factory=list)


def _load_all() -> dict[str, dict]:
    if not BRANDS_FILE.exists():
        return {}
    try:
        return json.loads(BRANDS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_all(data: dict[str, dict]) -> None:
    BRANDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    BRANDS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_brands() -> list[BrandPreset]:
    return [BrandPreset(**v) for v in _load_all().values()]


def get_brand(brand_id: str) -> Optional[BrandPreset]:
    data = _load_all()
    if brand_id not in data:
        return None
    return BrandPreset(**data[brand_id])


def create_brand(name: str) -> BrandPreset:
    bid = uuid.uuid4().hex[:10]
    preset = BrandPreset(brand_id=bid, name=name)
    data = _load_all()
    data[bid] = preset.model_dump()
    _save_all(data)
    (settings.workspace_path / "brands" / bid).mkdir(parents=True, exist_ok=True)
    return preset


def update_brand(brand_id: str, **fields) -> Optional[BrandPreset]:
    data = _load_all()
    if brand_id not in data:
        return None
    cur = data[brand_id]
    for k, v in fields.items():
        if v is not None:
            cur[k] = v
    data[brand_id] = cur
    _save_all(data)
    return BrandPreset(**cur)


def delete_brand(brand_id: str) -> bool:
    data = _load_all()
    if brand_id not in data:
        return False
    del data[brand_id]
    _save_all(data)
    import shutil
    folder = settings.workspace_path / "brands" / brand_id
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
    return True


def save_brand_asset(brand_id: str, kind: str, file_bytes: bytes, original_name: str) -> str:
    """kind: 'logo' | 'font'. 저장 후 파일명 반환"""
    if get_brand(brand_id) is None:
        raise ValueError("브랜드 없음")
    folder = settings.workspace_path / "brands" / brand_id
    folder.mkdir(parents=True, exist_ok=True)
    ext = Path(original_name).suffix.lower()
    safe_kind = kind.replace("/", "_")
    target = folder / f"{safe_kind}{ext}"
    target.write_bytes(file_bytes)
    # preset도 업데이트
    if kind == "logo":
        update_brand(brand_id, logo_filename=target.name)
    elif kind == "font":
        update_brand(brand_id, font_filename=target.name)
    return target.name


def get_brand_asset_path(brand_id: str, filename: str) -> Optional[Path]:
    if not filename:
        return None
    p = settings.workspace_path / "brands" / brand_id / filename
    return p if p.exists() else None


def apply_brand_to_concept(concept: dict, brand: BrandPreset) -> dict:
    """컨셉 dict에 브랜드 컬러 덮어쓰기 (얕은 복사)"""
    out = dict(concept)
    if brand.accent_color:
        out["accent_color"] = brand.accent_color
    if brand.sub_color:
        out["sub_color"] = brand.sub_color
    if brand.text_color:
        out["text_color"] = brand.text_color
    return out
