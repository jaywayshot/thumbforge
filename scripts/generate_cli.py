"""
ThumbForge CLI 배치 생성 도구
─ 서버/브라우저 없이 터미널에서 폴더(또는 단일 이미지)를 일괄 처리
─ 내부적으로 동일한 파이프라인(app.core.pipeline.run_generation)을 사용

사용 예:
  python scripts/generate_cli.py --input ./in --concept white_minimal \
      --platform coupang --variants 4 --output ./out
  python scripts/generate_cli.py -i product.png -o ./out
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# 직접 실행(python scripts/generate_cli.py) 시 프로젝트 루트를 import 경로에 추가
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.schemas import GenerateRequest, TextOption
from app.core.pipeline import run_generation
from app.services.storage import save_upload

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def collect_inputs(input_path: Path) -> list[Path]:
    """파일이면 그 파일, 폴더면 폴더 내 이미지들."""
    if input_path.is_file():
        return [input_path] if input_path.suffix.lower() in IMAGE_EXTS else []
    if input_path.is_dir():
        return sorted(p for p in input_path.iterdir()
                      if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
    return []


def process_one(
    src: Path,
    concept: str,
    platform: str,
    variants: int,
    out_dir: Path,
    category: str | None = None,
    text: dict | None = None,
) -> list[dict]:
    """이미지 1장 → variant 생성 → out_dir 에 복사. 결과 메타 리스트 반환."""
    out_dir.mkdir(parents=True, exist_ok=True)
    upload_id, _ = save_upload(src.read_bytes(), src.name)
    req = GenerateRequest(
        upload_id=upload_id,
        concept=concept,
        platform=platform,
        variants=variants,
        text=TextOption(**(text or {})),
        category_hint=category,
    )
    resp = run_generation(req)
    results: list[dict] = []
    for v in resp.variants:
        dst = out_dir / f"{src.stem}_{v.variant_id}.png"
        shutil.copyfile(v.file_path, dst)
        results.append({
            "source": src.name,
            "output": str(dst),
            "ctr_score": v.ctr_score,
            "qc_passed": v.qc_passed,
            "layout": v.layout_used,
        })
    return results


def run_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ThumbForge CLI 배치 썸네일 생성")
    parser.add_argument("-i", "--input", required=True, help="이미지 파일 또는 폴더")
    parser.add_argument("-o", "--output", default="./workspace/cli_out", help="결과 폴더")
    parser.add_argument("-c", "--concept", default="white_minimal", help="컨셉 이름")
    parser.add_argument("-p", "--platform", default="coupang", help="플랫폼 이름")
    parser.add_argument("-n", "--variants", type=int, default=4, help="이미지당 생성 개수")
    parser.add_argument("--category", default=None, help="카테고리 힌트(선택)")
    parser.add_argument("--headline", default=None, help="헤드라인(비우면 자동 추천)")
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    sources = collect_inputs(input_path)
    if not sources:
        print(f"[X] 처리할 이미지가 없습니다: {input_path}")
        return 1

    out_dir = Path(args.output)
    text = {"headline": args.headline} if args.headline else None

    total = 0
    print(f"입력 {len(sources)}장 → 컨셉={args.concept}, 플랫폼={args.platform}, "
          f"이미지당 {args.variants}장")
    for src in sources:
        try:
            results = process_one(src, args.concept, args.platform,
                                  args.variants, out_dir, args.category, text)
            total += len(results)
            best = max(results, key=lambda r: r["ctr_score"]) if results else None
            tag = f"(best CTR {best['ctr_score']})" if best else ""
            print(f"  ✓ {src.name}: {len(results)}장 {tag}")
        except Exception as e:
            print(f"  ✗ {src.name}: 실패 - {e}")

    print(f"완료: 총 {total}장 → {out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
