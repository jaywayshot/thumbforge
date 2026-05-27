"""
v2 통합 테스트
─ 브랜드 프리셋 생성 → 적용 → 컬러 덮어쓰기 확인
─ ZIP 일괄 처리 워커 직접 호출 검증
"""
import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# pydantic_settings 없을 때 폴백 (test_pipeline.py와 동일 패턴)
import types, os
os.environ.setdefault("WORKSPACE_DIR", str(ROOT / "workspace"))

try:
    from app.settings import settings
except ImportError:
    fake = types.SimpleNamespace(
        bg_provider="mock", text_provider="mock", qc_provider="mock",
        matting_model="u2net",
        openai_api_key="", stability_api_key="", gemini_api_key="", anthropic_api_key="",
        workspace_dir=str(ROOT / "workspace"), max_upload_mb=20,
        default_variants=4, output_size=1000,
        workspace_path=ROOT / "workspace",
        uploads_path=ROOT / "workspace" / "uploads",
        outputs_path=ROOT / "workspace" / "outputs",
        temp_path=ROOT / "workspace" / "temp",
        ensure_dirs=lambda: None,
    )
    for p in (fake.uploads_path, fake.outputs_path, fake.temp_path):
        p.mkdir(parents=True, exist_ok=True)
    fake_mod = types.ModuleType("app.settings")
    fake_mod.settings = fake
    fake_mod.BASE_DIR = ROOT
    fake_mod.CONFIG_DIR = ROOT / "config"
    sys.modules["app.settings"] = fake_mod

# pydantic 폴백 (테스트 환경에 없을 때)
try:
    import pydantic
except ImportError:
    # 최소한의 BaseModel/Field 대체
    fake_pyd = types.ModuleType("pydantic")
    class BaseModel:
        def __init__(self, **data):
            for k, v in data.items():
                setattr(self, k, v)
        def model_dump(self):
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
    def Field(default=None, default_factory=None, **kwargs):
        if default_factory is not None:
            return default_factory()
        return default
    fake_pyd.BaseModel = BaseModel
    fake_pyd.Field = Field
    sys.modules["pydantic"] = fake_pyd

from PIL import Image, ImageDraw


def make_fake_product(size=400, color=(220, 50, 50)) -> Image.Image:
    img = Image.new("RGB", (size, size), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    pad = size // 8
    draw.ellipse([pad, pad, size - pad, size - pad], fill=color)
    return img


def make_zip_with_products(num: int = 3) -> bytes:
    """num 개 가짜 제품을 ZIP으로 (대량 처리 테스트용)"""
    buf = io.BytesIO()
    colors = [(220, 50, 50), (50, 200, 80), (50, 100, 220)]
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i in range(num):
            img = make_fake_product(400, colors[i % len(colors)])
            img_buf = io.BytesIO()
            img.save(img_buf, "PNG")
            zf.writestr(f"product_{i+1}.png", img_buf.getvalue())
    return buf.getvalue()


def test_brand_preset():
    print("\n=== 브랜드 프리셋 적용 ===")
    from app.services.brand_store import (
        create_brand, update_brand, get_brand, delete_brand, apply_brand_to_concept
    )
    from app.services.concept_loader import get_concept

    brand = create_brand("내 테스트 브랜드")
    assert brand.brand_id
    print(f"  생성: {brand.brand_id} - {brand.name}")

    updated = update_brand(brand.brand_id,
                          accent_color="#FF00FF",
                          text_color="#00FF00",
                          default_headline="우리 브랜드 슬로건")
    assert updated.accent_color == "#FF00FF"
    print(f"  업데이트: accent={updated.accent_color}, text={updated.text_color}")

    concept = get_concept("coupang_sales")
    original_accent = concept.get("accent_color")
    applied = apply_brand_to_concept(concept, updated)
    assert applied["accent_color"] == "#FF00FF"
    assert original_accent != "#FF00FF"
    print(f"  덮어쓰기: 원본 accent {original_accent} → 브랜드 {applied['accent_color']}")

    # 정리
    assert delete_brand(brand.brand_id)
    print("  ✓ 브랜드 적용 검증 통과")


def test_bulk_worker():
    print("\n=== 대량 처리 워커 (인라인 실행) ===")
    from app.jobs.bulk_worker import run_bulk_job
    from app.jobs.registry import registry, JobStatus

    zip_bytes = make_zip_with_products(3)
    print(f"  가짜 ZIP 생성: {len(zip_bytes)} bytes (3개 이미지)")

    job = registry.create(kind="bulk_generate")
    print(f"  job_id: {job.job_id}")

    # 동기로 실행 (테스트에서는 백그라운드 없이)
    run_bulk_job(
        job_id=job.job_id,
        zip_bytes=zip_bytes,
        concept="white_minimal",
        platform="coupang",
        variants_per_image=2,
        text={"headline": "테스트 헤드라인"},
    )

    final = registry.get(job.job_id)
    print(f"  상태: {final.status}")
    print(f"  진행: {final.done}/{final.total} ({final.progress*100:.0f}%)")
    print(f"  메시지: {final.message}")

    assert final.status == JobStatus.SUCCESS, f"실패: {final.error}"
    assert final.result["succeeded"] == 3
    assert final.result["total_images"] == 3

    # 결과 ZIP 확인
    zip_path = ROOT / "workspace" / "outputs" / "bulk" / f"{job.job_id}.zip"
    assert zip_path.exists(), f"결과 ZIP 없음: {zip_path}"
    print(f"  결과 ZIP: {zip_path} ({zip_path.stat().st_size} bytes)")

    # ZIP 내용 검증
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        png_count = sum(1 for n in names if n.endswith(".png"))
        print(f"  ZIP 내부: {png_count}개 PNG + _summary.json")
        assert png_count == 6, f"기대 6개(3제품×2variants), 실제 {png_count}"
        assert "_summary.json" in names

    print("  ✓ 대량 처리 검증 통과")


def test_qc_enhancements():
    print("\n=== QC 강화 (saliency / color diversity) ===")
    from app.core.qc import _saliency_score, _color_diversity_score, estimate_ctr_score

    # 검정 중앙 + 흰 외곽 → 시선 집중도 높음
    img = Image.new("RGB", (200, 200), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.ellipse([50, 50, 150, 150], fill=(0, 0, 0))
    sal = _saliency_score(img)
    div = _color_diversity_score(img)
    print(f"  중앙 집중 이미지: saliency={sal}, diversity={div}")
    assert sal > 30

    ctr = estimate_ctr_score(img, {"passed": True, "text_legibility": 90},
                             has_discount=True, has_badge=True)
    print(f"  CTR 종합 점수: {ctr}")
    assert 0 <= ctr <= 100

    print("  ✓ QC 강화 검증 통과")


if __name__ == "__main__":
    test_brand_preset()
    test_qc_enhancements()
    test_bulk_worker()
    print("\n✅ v2 통합 테스트 전체 통과")
