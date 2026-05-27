"""
파일 저장소 - 업로드 ID 기반 관리
"""
import uuid
from pathlib import Path
from typing import Optional

from PIL import Image

from app.settings import settings


def new_upload_id() -> str:
    return uuid.uuid4().hex[:12]


def new_job_id() -> str:
    return uuid.uuid4().hex[:12]


def save_upload(file_bytes: bytes, original_filename: str) -> tuple[str, Path]:
    upload_id = new_upload_id()
    ext = Path(original_filename).suffix.lower() or ".png"
    if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
        ext = ".png"
    target = settings.uploads_path / f"{upload_id}{ext}"
    target.write_bytes(file_bytes)
    return upload_id, target


def find_upload(upload_id: str) -> Optional[Path]:
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        p = settings.uploads_path / f"{upload_id}{ext}"
        if p.exists():
            return p
    return None


def job_output_dir(job_id: str) -> Path:
    p = settings.outputs_path / job_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def open_image(path: Path) -> Image.Image:
    """RGBA로 정규화해서 로드"""
    img = Image.open(path)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return img
