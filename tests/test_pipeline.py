"""
핵심 합성 로직 통합 테스트 (FastAPI / rembg 없이도 실행)
─ 가짜 제품 이미지를 만들고
─ 누끼 폴백 → 배경 생성 → 합성 → 저장
─ 까지 end-to-end 동작 확인
"""
import sys
from pathlib import Path

# 프로젝트 루트 경로
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# pydantic_settings 없어도 임포트 가능하게 우회용 settings 모킹
import types
import os
os.environ.setdefault("WORKSPACE_DIR", str(ROOT / "workspace"))

# 가짜 settings 모듈 (pydantic_settings 미설치 환경 대응)
try:
    from app.settings import settings  # 정상 경로
except ImportError:
    fake = types.SimpleNamespace(
        bg_provider="mock",
        text_provider="mock",
        qc_provider="mock",
        matting_model="u2net",
        openai_api_key="",
        stability_api_key="",
        gemini_api_key="",
        anthropic_api_key="",
        workspace_dir=str(ROOT / "workspace"),
        max_upload_mb=20,
        default_variants=4,
        output_size=1000,
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

from PIL import Image, ImageDraw

from app.core.matting import remove_background, crop_to_content
from app.core.layout import build_layout
from app.core.composer import compose_thumbnail
from app.providers.mock import MockBackgroundProvider, MockTextSuggestionProvider, MockQCProvider
from app.services.concept_loader import get_concept, get_concepts


def make_fake_product(size=400) -> Image.Image:
    """흰 배경 위의 빨간 원 = 누끼 대상이 될 가짜 제품"""
    img = Image.new("RGB", (size, size), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    pad = size // 8
    draw.ellipse([pad, pad, size - pad, size - pad], fill=(220, 50, 50))
    draw.ellipse([pad + 30, pad + 30, size - pad - 80, size - pad - 80], fill=(255, 100, 100))
    return img


def make_alpha_product(size=400) -> Image.Image:
    """이미 누끼된 가짜 제품 (RGBA)"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = size // 8
    draw.ellipse([pad, pad, size - pad, size - pad], fill=(50, 100, 220, 255))
    return img


def test_full_pipeline():
    print("\n=== 컨셉 로더 ===")
    concepts = get_concepts()
    print(f"로드된 컨셉: {len(concepts)}개 → {list(concepts.keys())[:3]}...")
    assert len(concepts) > 0

    print("\n=== 누끼 (폴백 모드: 흰배경 자동 제거) ===")
    product_with_bg = make_fake_product(400)
    nukii = remove_background(product_with_bg)
    print(f"  결과 모드: {nukii.mode}, 크기: {nukii.size}")
    assert nukii.mode == "RGBA"
    nukii = crop_to_content(nukii, padding=10)
    print(f"  컨텐츠 크롭 후: {nukii.size}")

    print("\n=== 이미 알파 있는 이미지 ===")
    alpha_product = make_alpha_product(400)
    nukii2 = remove_background(alpha_product)
    assert nukii2.mode == "RGBA"
    print("  통과 (이미 알파가 있으면 그대로 반환)")

    print("\n=== Mock Provider 배경 생성 ===")
    bg_provider = MockBackgroundProvider()
    out_dir = ROOT / "workspace" / "outputs" / "_test"
    out_dir.mkdir(parents=True, exist_ok=True)

    test_concepts = ["coupang_sales", "premium_luxury", "tech_electronics",
                     "white_minimal", "discount_event", "summer", "kids", "apple_style"]
    text_provider = MockTextSuggestionProvider()
    qc = MockQCProvider()

    for concept_name in test_concepts:
        concept = get_concept(concept_name)
        bg = bg_provider.generate(1000, 1000, concept, seed=42)
        layout = build_layout(concept.get("layout", "center_product"), 1000, 1000)

        suggestion = text_provider.suggest("general", concept_name)

        final = compose_thumbnail(
            background=bg,
            product_rgba=nukii,
            layout=layout,
            concept=concept,
            headline=suggestion["headline"],
            sub_text=suggestion["sub_text"],
            badge=suggestion["badge"],
            discount_percent=30 if "sale" in concept_name or "discount" in concept_name else None,
        )

        report = qc.review(final, {"platform": "coupang"})

        out_path = out_dir / f"test_{concept_name}.png"
        final.convert("RGBA").save(out_path, "PNG", optimize=True)
        print(f"  ✓ {concept_name:20s} → {out_path.name}  "
              f"(QC: {'PASS' if report['passed'] else 'WARN'}, contrast={report['contrast_score']})")

    print("\n✅ 전체 통합 테스트 통과")
    print(f"   결과물: {out_dir}")


if __name__ == "__main__":
    test_full_pipeline()
