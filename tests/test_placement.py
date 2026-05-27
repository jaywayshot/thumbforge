"""
카테고리 배치 + composer 통합 + scene 파이프라인 테스트

기본 테스트는 실제 이미지 API 를 호출하지 않는다(배경 provider 를 monkeypatch).
실호출 통합 테스트는 RUN_LIVE_IMAGE_TEST=true 일 때만.
"""
import io
import os
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image

import app.providers.stability_provider as sp
from app.core.composer import compose_thumbnail
from app.core.layout import build_layout
from app.core.placement import compute_position, get_placement_rules
from app.models.schemas import GenerateRequest, ProductInfo
from app.services.storage import save_upload


# ───────── placement 규칙 ─────────

def test_placement_rules_all_categories():
    cats = ["가구", "의류", "식품", "전자제품", "뷰티", "액세서리", "생활용품", "기타"]
    for cat in cats:
        r = get_placement_rules(cat)
        assert r.anchor in ("bottom", "center", "top"), (cat, r.anchor)
        assert 0 < r.size_ratio <= 1.0
        assert r.shadow_blur >= 0 and 0 <= r.shadow_opacity <= 255
    # 가구=바닥/강한그림자, 의류 상의=top
    assert get_placement_rules("가구", "소파").anchor == "bottom"
    assert get_placement_rules("의류", "상의").anchor == "top"
    assert get_placement_rules("의류", "신발").size_ratio == 0.40
    print("  ✓ 8 카테고리 placement 규칙 유효")


def test_compute_position_anchors():
    rb = get_placement_rules("가구", "테이블")   # bottom
    x, y = compute_position(rb, 1000, 1000, 400, 300)
    assert y + 300 <= 1000 and x == 300  # 바닥 근처, 가로 중앙
    rt = get_placement_rules("의류", "상의")     # top
    _, yt = compute_position(rt, 1000, 1000, 400, 300)
    assert yt <= 200
    print("  ✓ anchor별 위치 계산(bottom/top)")


def test_composer_with_placement():
    bg = Image.new("RGB", (600, 600), (225, 218, 205))
    prod = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    prod.paste((150, 100, 60, 255), (60, 60, 240, 240))
    lay = build_layout("center_product", 600, 600)
    rule = get_placement_rules("가구", "책상")
    out = compose_thumbnail(bg, prod, lay, {"text_color": "#111"}, headline="원목 책상", placement=rule)
    assert out.size == (600, 600) and out.mode == "RGBA"
    print("  ✓ composer placement 통합 합성")


# ───────── scene 파이프라인 (API 없이 monkeypatch) ─────────

@contextmanager
def _patched_scene_provider():
    """StabilityBackgroundProvider.generate 를 로컬 그라데이션으로 교체(실호출 차단)."""
    orig = sp.StabilityBackgroundProvider.generate

    def fake(self, width, height, concept, seed=0, prompt=None):
        # 대비/색 다양성이 충분한 가짜 배경(QC 통과용)
        import numpy as np
        arr = np.zeros((height, width, 3), dtype=np.uint8)
        arr[..., 0] = np.linspace(180, 240, width)[None, :]
        arr[..., 1] = np.linspace(160, 220, height)[:, None]
        arr[..., 2] = 200
        return Image.fromarray(arr, "RGB")

    sp.StabilityBackgroundProvider.generate = fake
    try:
        yield
    finally:
        sp.StabilityBackgroundProvider.generate = orig


def _make_upload() -> str:
    buf = io.BytesIO()
    im = Image.new("RGB", (300, 300), (255, 255, 255))
    im.paste((120, 90, 60), (80, 80, 220, 220))
    im.save(buf, "PNG")
    uid, _ = save_upload(buf.getvalue(), "desk.png")
    return uid


def test_scene_pipeline_mode():
    from app.core.pipeline import run_generation
    uid = _make_upload()
    req = GenerateRequest(
        upload_id=uid, concept="white_minimal", platform="coupang", variants=1,
        fresh=True,
        product_info=ProductInfo(category="가구", sub_category="책상", material="원목",
                                 color="화이트", use_space="서재", mood_keywords=["미니멀"]),
    )
    with _patched_scene_provider():
        resp = run_generation(req)
    assert resp.bg_mode == "scene"
    assert resp.scene_positive and "no product in frame" in resp.scene_positive
    assert len(resp.variants) == 1
    v = resp.variants[0]
    assert 0 <= v.ctr_score <= 100 and v.file_url.startswith("/files/")
    print(f"  ✓ scene 파이프라인(mock provider): bg_mode={resp.bg_mode}, ctr={v.ctr_score}")


def test_non_scene_pipeline_unchanged():
    from app.core.pipeline import run_generation
    uid = _make_upload()
    req = GenerateRequest(upload_id=uid, concept="white_minimal", platform="coupang", variants=1)
    resp = run_generation(req)  # product_info 없음 → 기존 mock 경로
    assert resp.bg_mode == "mock" and resp.scene_positive is None
    print("  ✓ product_info 없으면 기존 mock 경로 유지")


# ───────── 실호출 통합 (옵트인) ─────────

def test_live_image_optional():
    if os.environ.get("RUN_LIVE_IMAGE_TEST") != "true":
        print("  · (skip) 실 이미지 생성은 RUN_LIVE_IMAGE_TEST=true 일 때만")
        return
    from app.core.scene_prompt import build_scene_prompt
    from app.providers.openai_provider import OpenAIBackgroundProvider
    from app.providers.stability_provider import StabilityBackgroundProvider
    from app.services.concept_loader import get_concept

    pi = ProductInfo(category="가구", sub_category="책상", material="원목", color="화이트",
                     use_space="서재", mood_keywords=["미니멀", "북유럽"])
    pos, neg = build_scene_prompt(pi, get_concept("white_minimal"), "coupang", concept_id="white_minimal")
    # 이미지 생성은 텍스트보다 비싸다(1장 ~5-6원). 합리적 상한으로 성공 여부만 검증.
    st = StabilityBackgroundProvider().generate(1024, 1024, get_concept("white_minimal"),
                                                seed=1, prompt=(pos, neg))
    assert st.size == (1024, 1024)
    oa = OpenAIBackgroundProvider()
    if oa._client is not None:
        da = oa.generate(1024, 1024, get_concept("white_minimal"), seed=1, prompt=(pos, neg))
        assert da.size == (1024, 1024)
    print("  ✓ LIVE: Stability + DALL-E 1회씩 생성 성공")


if __name__ == "__main__":
    print("\n=== placement / scene 파이프라인 테스트 ===")
    test_placement_rules_all_categories()
    test_compute_position_anchors()
    test_composer_with_placement()
    test_scene_pipeline_mode()
    test_non_scene_pipeline_unchanged()
    test_live_image_optional()
    print("\n✅ placement / scene 파이프라인 테스트 전체 통과")
