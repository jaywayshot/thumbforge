"""
레퍼런스 이미지 분석/저장 (스타일 가이드)

사용자가 "이런 느낌" 이미지를 올리면 로컬에서만 분석한다(외부 전송 없음):
─ dominant 컬러 3개(hex)
─ 톤(밝음/어두움 × 유채/무채) → 영문 tone + 무드 키워드
분석 결과는 workspace/temp/reference/<ref_id>.json 에 저장하고,
generate 요청의 reference_id 로 scene_prompt 에 주입한다.

이미지 분석은 기존 경쟁사 분석기 함수를 재사용(신규 의존성 없음).
"""
from __future__ import annotations

import io
import json
import uuid
from pathlib import Path
from typing import Optional

from PIL import Image

from app.analyzers.competitor import classify_bg_tone, quantize_dominant_colors
from app.settings import settings


def _dir() -> Path:
    p = settings.temp_path / "reference"
    p.mkdir(parents=True, exist_ok=True)
    return p


def analyze_reference(image: Image.Image) -> dict:
    """레퍼런스 이미지 → 색/톤/무드 (로컬 분석)."""
    colors = quantize_dominant_colors(image, k=4)[:3]
    tone = classify_bg_tone(image)  # {brightness, chroma, label}

    bright = tone.get("brightness") == "밝음"
    chromatic = tone.get("chroma") == "유채"
    tone_en = ("bright airy" if bright else "dark moody")
    moods = []
    moods.append("airy bright" if bright else "moody dramatic")
    moods.append("vibrant colorful" if chromatic else "minimal neutral")

    return {
        "dominant_hex": [c["hex"] for c in colors],
        "tone": tone_en,
        "tone_label": tone.get("label"),
        "moods": moods,
    }


def save_reference(data: dict) -> str:
    ref_id = uuid.uuid4().hex[:12]
    with open(_dir() / f"{ref_id}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return ref_id


def load_reference(ref_id: str) -> Optional[dict]:
    if not ref_id:
        return None
    p = _dir() / f"{ref_id}.json"
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def analyze_bytes(data: bytes) -> dict:
    img = Image.open(io.BytesIO(data))
    img.load()
    return analyze_reference(img)
