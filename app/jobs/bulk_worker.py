"""
대량(Bulk) 처리 워커
─ ZIP 업로드 → 이미지들 추출 → 각각 N variant 생성 → 결과 ZIP
─ 진행률은 JobRegistry로 보고
"""
from __future__ import annotations

import shutil
import traceback
import zipfile
from pathlib import Path
from typing import Optional

from PIL import Image

from app.core.pipeline import run_generation
from app.jobs.registry import JobStatus, registry
from app.models.schemas import GenerateRequest, TextOption
from app.services.storage import save_upload
from app.settings import settings


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def _safe_name(name: str) -> str:
    """ZIP 안전 파일명 (디렉토리 traversal 방어)"""
    name = name.replace("\\", "/")
    if name.startswith("/") or ".." in name.split("/"):
        return ""
    return name


def extract_images_from_zip(zip_bytes: bytes, work_dir: Path) -> list[Path]:
    """ZIP에서 이미지만 추출. 디렉토리 traversal 방어."""
    work_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    with zipfile.ZipFile(zip_bytes, "r") if isinstance(zip_bytes, Path) else zipfile.ZipFile(
        __import__("io").BytesIO(zip_bytes), "r"
    ) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            safe = _safe_name(info.filename)
            if not safe:
                continue
            ext = Path(safe).suffix.lower()
            if ext not in IMAGE_EXTS:
                continue
            # 평탄화 (서브폴더 무시)
            flat_name = Path(safe).name
            target = work_dir / flat_name
            counter = 1
            while target.exists():
                target = work_dir / f"{Path(flat_name).stem}_{counter}{ext}"
                counter += 1
            with zf.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted.append(target)
    return extracted


def package_results_zip(out_zip_path: Path, items: list[dict]) -> None:
    """각 입력에 대한 variant 파일들을 하나의 ZIP으로 묶기"""
    out_zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in items:
            source_stem = item["source_stem"]
            for v in item["variants"]:
                vp = Path(v["file_path"])
                if vp.exists():
                    arcname = f"{source_stem}/{vp.name}"
                    zf.write(vp, arcname=arcname)
        # 결과 요약 JSON 동봉
        import json
        summary = json.dumps(items, ensure_ascii=False, indent=2)
        zf.writestr("_summary.json", summary)


def run_bulk_job(
    job_id: str,
    zip_bytes: bytes,
    concept: str,
    platform: str,
    variants_per_image: int,
    text: Optional[dict] = None,
    category_hint: Optional[str] = None,
) -> None:
    """
    백그라운드에서 호출됨.
    job_id 의 JobRecord를 업데이트.
    """
    try:
        registry.update(job_id, status=JobStatus.RUNNING, message="ZIP 추출 중...")

        bulk_dir = settings.temp_path / "bulk" / job_id
        if bulk_dir.exists():
            shutil.rmtree(bulk_dir)
        bulk_dir.mkdir(parents=True, exist_ok=True)

        sources = extract_images_from_zip(zip_bytes, bulk_dir / "src")
        if not sources:
            registry.fail(job_id, "ZIP 안에서 이미지를 찾을 수 없습니다 (PNG/JPG/WEBP)")
            return

        registry.update(job_id, total=len(sources), message=f"{len(sources)}개 이미지 처리 시작")

        text_opt = TextOption(**(text or {}))
        results: list[dict] = []

        for idx, src_path in enumerate(sources, 1):
            try:
                registry.update(job_id, message=f"[{idx}/{len(sources)}] {src_path.name}")

                # 업로드 시스템에 등록
                file_bytes = src_path.read_bytes()
                upload_id, _ = save_upload(file_bytes, src_path.name)

                req = GenerateRequest(
                    upload_id=upload_id,
                    concept=concept,
                    platform=platform,
                    variants=variants_per_image,
                    text=text_opt,
                    category_hint=category_hint,
                )
                resp = run_generation(req)
                results.append({
                    "source_filename": src_path.name,
                    "source_stem": src_path.stem,
                    "job_id_inner": resp.job_id,
                    "variants": [v.model_dump() for v in resp.variants],
                    "elapsed_ms": resp.elapsed_ms,
                })
            except Exception as e:
                results.append({
                    "source_filename": src_path.name,
                    "source_stem": src_path.stem,
                    "error": str(e),
                    "variants": [],
                })
            finally:
                registry.tick(job_id)

        # 결과 ZIP 패키징
        out_zip = settings.outputs_path / "bulk" / f"{job_id}.zip"
        package_results_zip(out_zip, results)

        registry.finish(job_id, result={
            "result_zip_url": f"/files/bulk/{job_id}.zip",
            "total_images": len(sources),
            "succeeded": sum(1 for r in results if r["variants"]),
            "failed": sum(1 for r in results if not r["variants"]),
            "per_image": results,
        })

        # 임시 추출 폴더 정리
        try:
            shutil.rmtree(bulk_dir)
        except Exception:
            pass

    except Exception as e:
        registry.fail(job_id, f"{e}\n{traceback.format_exc()}")
