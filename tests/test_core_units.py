"""
코어 모듈 단위 테스트 (layout / composer / qc / storage)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import io
from PIL import Image, ImageDraw

from app.core.layout import build_layout, variants_for, LAYOUT_VARIANTS, Box
from app.core.composer import compose_thumbnail
from app.core import qc
from app.providers.mock import MockBackgroundProvider
from app.services.concept_loader import get_concept
from app.services import storage


# ───────── layout ─────────

def _box_in_bounds(b: Box, W: int, H: int) -> bool:
    return (b.w > 0 and b.h > 0 and 0 <= b.x and 0 <= b.y
            and b.x + b.w <= W and b.y + b.h <= H)


def test_all_layouts_in_bounds():
    W = H = 1000
    for name in LAYOUT_VARIANTS:
        lay = build_layout(name, W, H)
        assert lay.name == name
        for b in (lay.product_box, lay.headline_box, lay.sub_box):
            assert _box_in_bounds(b, W, H), f"{name}: box 범위 벗어남 {b}"
    print(f"  ✓ {len(LAYOUT_VARIANTS)}개 레이아웃 박스 범위 정상")


def test_layout_fallback_and_variants():
    lay = build_layout("does_not_exist", 800, 800)
    assert lay.name == "does_not_exist"          # 이름 보존 + 기본 박스
    assert _box_in_bounds(lay.product_box, 800, 800)
    for name in LAYOUT_VARIANTS:
        vs = variants_for(name)
        assert isinstance(vs, list) and name in vs
    assert variants_for("unknown")[0] == "unknown"
    print("  ✓ 미지원 레이아웃 폴백 + variants_for 동작")


# ───────── composer ─────────

def _product_rgba(size=300) -> Image.Image:
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse([20, 20, size - 20, size - 20], fill=(50, 120, 220, 255))
    return im


def test_compose_size_and_mode():
    concept = get_concept("white_minimal")
    bg = MockBackgroundProvider().generate(1000, 1000, concept, seed=1)
    lay = build_layout("center_product", 1000, 1000)
    out = compose_thumbnail(bg, _product_rgba(), lay, concept,
                            headline="오늘의 추천", sub_text="빠른 배송",
                            badge="NEW", discount_percent=30)
    assert out.size == (1000, 1000)
    assert out.mode == "RGBA"
    print(f"  ✓ compose_thumbnail → {out.size} {out.mode}")


def test_compose_does_not_mutate_product():
    """핵심 원칙: 제품 원본 훼손 금지 → 입력 product_rgba 가 변하지 않아야 함."""
    concept = get_concept("coupang_sales")
    bg = MockBackgroundProvider().generate(800, 800, concept, seed=2)
    lay = build_layout("left_product_right_text", 800, 800)
    product = _product_rgba()
    before = product.tobytes()
    compose_thumbnail(bg, product, lay, concept, headline="테스트")
    assert product.tobytes() == before, "compose 가 원본 제품을 변형함"
    print("  ✓ 제품 원본 불변 확인")


# ───────── qc ─────────

def test_ctr_score_bounds():
    for color in ((10, 10, 10), (128, 128, 128), (250, 250, 250)):
        img = Image.new("RGB", (400, 400), color)
        ImageDraw.Draw(img).rectangle([100, 100, 300, 300], fill=(255 - color[0],) * 3)
        for hd in (True, False):
            s = qc.estimate_ctr_score(img, {"passed": True, "text_legibility": 80},
                                      has_discount=hd, has_badge=hd)
            assert 0 <= s <= 100, f"CTR 점수 범위 이탈: {s}"
    div = qc._color_diversity_score(Image.new("RGB", (64, 64), (10, 200, 30)))
    assert 0 <= div <= 100
    sal = qc._saliency_score(Image.new("RGB", (200, 200), (255, 255, 255)))
    assert sal >= 0
    print("  ✓ CTR/색다양성/시선집중 점수 범위 정상")


def test_validate_text_forbidden_and_warning():
    forbidden, warnings = qc.validate_text("최저가 특가", "무료배송 당일출고", "coupang")
    assert "최저가" in forbidden
    assert "무료배송" in warnings
    ok_f, ok_w = qc.validate_text("오늘의 추천", "빠른 배송", "coupang")
    assert ok_f == []
    print(f"  ✓ validate_text: 금지 {forbidden}, 주의 {warnings}")


# ───────── storage ─────────

def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (120, 90), (200, 50, 50)).save(buf, "PNG")
    return buf.getvalue()


def test_storage_roundtrip_and_ext_normalize():
    uid, path = storage.save_upload(_png_bytes(), "thing.PNG")
    assert path.exists()
    assert storage.find_upload(uid) == path

    # 미지원 확장자는 .png 로 정규화
    uid2, path2 = storage.save_upload(_png_bytes(), "thing.gif")
    assert path2.suffix == ".png"
    assert storage.find_upload(uid2) == path2

    # 없는 id
    assert storage.find_upload("ffffffffffff") is None

    # job_output_dir 생성 + open_image RGBA
    jid = storage.new_job_id()
    out = storage.job_output_dir(jid)
    assert out.exists() and out.is_dir()
    img = storage.open_image(path)
    assert img.mode == "RGBA"
    print(f"  ✓ storage 라운드트립 + 확장자 정규화 + open_image RGBA")


if __name__ == "__main__":
    print("\n=== 코어 단위 테스트 ===")
    test_all_layouts_in_bounds()
    test_layout_fallback_and_variants()
    test_compose_size_and_mode()
    test_compose_does_not_mutate_product()
    test_ctr_score_bounds()
    test_validate_text_forbidden_and_warning()
    test_storage_roundtrip_and_ext_normalize()
    print("\n✅ 코어 단위 테스트 전체 통과")
