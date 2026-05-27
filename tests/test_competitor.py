"""
경쟁사 분석 모듈 테스트
─ 모킹된 HTML로 썸네일 URL 파싱 검증
─ 색상 추출 / 배경 톤 / 뱃지 검출 단위 테스트
─ 캐시 동작(저장/조회/만료) 검증
─ 네트워크 주입(mock)으로 analyze_competitor 파이프라인 검증
─ robots.txt 차단 동작 검증
─ 실제 쿠팡 호출은 RUN_LIVE_TESTS=true 일 때만
"""
import io
import os
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.analyzers import cache as comp_cache
from app.analyzers.competitor import (
    HARD_MAX_ITEMS,
    RobotsBlockedError,
    aggregate_results,
    analyze_competitor,
    analyze_single_image,
    classify_bg_tone,
    detect_discount_badge,
    estimate_text_area_ratio,
    is_allowed_by_robots,
    parse_thumbnail_urls,
    quantize_dominant_colors,
    suggest_concepts_from_analysis,
)
from app.services.concept_loader import get_concepts


# ───────── 헬퍼 ─────────

def _png(color=(255, 255, 255), size=(200, 200)) -> Image.Image:
    return Image.new("RGB", size, color)


def _png_bytes(color=(255, 255, 255), size=(200, 200)) -> bytes:
    buf = io.BytesIO()
    _png(color, size).save(buf, "PNG")
    return buf.getvalue()


COUPANG_HTML = """
<html><body>
<ul id="productList">
  <li class="search-product">
    <img class="search-product-wrap-img" data-img-src="//img1.coupangcdn.com/thumbnails/a.jpg" src="placeholder.gif">
  </li>
  <li class="search-product">
    <img class="search-product-wrap-img" src="https://img1.coupangcdn.com/thumbnails/b.jpg">
  </li>
  <li class="search-product">
    <img class="search-product-wrap-img" data-img-src="data:image/gif;base64,AAAA">
  </li>
</ul>
</body></html>
"""


# ───────── HTML 파싱 ─────────

def test_parse_thumbnail_urls():
    urls = parse_thumbnail_urls(COUPANG_HTML, base_url="https://www.coupang.com/np/search?q=x")
    # data: URL 은 제외, 상대경로(//)는 절대화
    assert "https://img1.coupangcdn.com/thumbnails/a.jpg" in urls
    assert "https://img1.coupangcdn.com/thumbnails/b.jpg" in urls
    assert all(not u.startswith("data:") for u in urls)
    assert len(urls) == 2
    print(f"  ✓ 썸네일 URL 파싱: {len(urls)}개 추출")


def test_parse_empty_html():
    assert parse_thumbnail_urls("<html><body>no products</body></html>", "https://x.com") == []
    print("  ✓ 상품 없는 HTML → 빈 리스트")


# ───────── 색상 추출 ─────────

def test_quantize_dominant_colors():
    colors = quantize_dominant_colors(_png((220, 30, 30)), k=5)
    assert len(colors) >= 1
    top = colors[0]
    r, g, b = top["rgb"]
    assert r > 180 and g < 80 and b < 80, top
    assert top["ratio"] > 0.9  # 단색이므로 1개 색이 압도적
    assert top["hex"].startswith("#")
    print(f"  ✓ dominant 컬러 추출: {top['hex']} ({top['ratio']})")


# ───────── 배경 톤 ─────────

def test_classify_bg_tone():
    assert classify_bg_tone(_png((255, 255, 255)))["label"] == "밝음/무채"
    assert classify_bg_tone(_png((10, 10, 10)))["label"] == "어두움/무채"
    red = classify_bg_tone(_png((230, 20, 20)))
    assert red["chroma"] == "유채"
    print("  ✓ 배경 톤: 흰색→밝음/무채, 검정→어두움/무채, 빨강→유채")


# ───────── 텍스트 영역 비율 ─────────

def test_estimate_text_area_ratio():
    blank = estimate_text_area_ratio(_png((255, 255, 255)))
    rng = np.random.default_rng(0)
    noisy_arr = rng.integers(0, 256, (200, 200, 3), dtype=np.uint8)
    noisy = estimate_text_area_ratio(Image.fromarray(noisy_arr, "RGB"))
    assert blank < 0.01
    assert noisy > blank
    print(f"  ✓ 텍스트 영역 추정: blank={blank} < noisy={noisy}")


# ───────── 할인 뱃지 ─────────

def test_detect_discount_badge():
    plain = detect_discount_badge(_png((255, 255, 255)))
    assert plain["has_badge"] is False

    # 우상단에 빨간 사각형(뱃지 모사)
    im = _png((255, 255, 255))
    arr = np.asarray(im).copy()
    arr[10:60, 140:190] = [220, 20, 20]
    badge = detect_discount_badge(Image.fromarray(arr, "RGB"))
    assert badge["has_badge"] is True, badge
    print(f"  ✓ 할인 뱃지 검출: plain={plain['has_badge']}, red-blob={badge['has_badge']}")


# ───────── 추천 컨셉 ─────────

def test_suggest_concepts_are_real():
    available = set(get_concepts().keys())

    # 빨강 우세 + 뱃지 多 → 쿠팡/할인 계열
    agg_sale = {
        "bg_tone_distribution": {"밝음/유채": 10},
        "badge_ratio": 0.8,
        "avg_text_area_ratio": 0.2,
        "dominant_colors": [{"hex": "#E01010", "rgb": [224, 16, 16], "weight": 0.5}],
    }
    recos = suggest_concepts_from_analysis(agg_sale)
    assert recos, "추천이 비어있음"
    assert all(c in available for c in recos), recos
    assert "coupang_sales" in recos or "discount_event" in recos

    # 어두운 배경 → 프리미엄 계열
    agg_dark = {
        "bg_tone_distribution": {"어두움/무채": 10},
        "badge_ratio": 0.0,
        "avg_text_area_ratio": 0.05,
        "dominant_colors": [{"hex": "#101010", "rgb": [16, 16, 16], "weight": 0.9}],
    }
    dark_recos = suggest_concepts_from_analysis(agg_dark)
    assert all(c in available for c in dark_recos), dark_recos
    assert "premium_luxury" in dark_recos or "black_luxury" in dark_recos
    print(f"  ✓ 추천 컨셉 실존 검증: sale={recos}, dark={dark_recos}")


def test_aggregate_empty():
    agg = aggregate_results([])
    assert agg["analyzed_count"] == 0
    assert agg["dominant_colors"] == []
    print("  ✓ 빈 입력 집계 안전")


# ───────── robots.txt ─────────

def test_robots_disallow_and_allow():
    block = "User-agent: *\nDisallow: /np/search"
    allow = "User-agent: *\nDisallow: /admin"
    url = "https://www.coupang.com/np/search?q=tumbler"
    assert is_allowed_by_robots(url, robots_text=block) is False
    assert is_allowed_by_robots(url, robots_text=allow) is True
    print("  ✓ robots.txt 차단/허용 판정")


def test_analyze_blocked_raises():
    block = "User-agent: *\nDisallow: /"
    try:
        analyze_competitor(
            "https://www.coupang.com/np/search?q=x",
            robots_text=block,
            html_fetcher=lambda u: COUPANG_HTML,
            image_fetcher=lambda u: _png_bytes(),
        )
        assert False, "RobotsBlockedError 가 발생해야 함"
    except RobotsBlockedError:
        pass
    print("  ✓ robots 차단 시 RobotsBlockedError")


# ───────── 파이프라인 (네트워크 주입) ─────────

def test_analyze_competitor_with_mocks():
    colors = [(220, 30, 30), (240, 240, 240), (20, 20, 20)]
    calls = {"img": 0}

    def img_fetcher(u):
        c = colors[calls["img"] % len(colors)]
        calls["img"] += 1
        return _png_bytes(c)

    res = analyze_competitor(
        "https://www.coupang.com/np/search?q=x",
        max_items=20,
        respect_robots=False,
        html_fetcher=lambda u: COUPANG_HTML,
        image_fetcher=img_fetcher,
    )
    assert res["analyzed_count"] == 2  # data: 제외하고 2개
    assert res["thumbnails_found"] == 2
    assert res["fetch_failed"] == 0
    assert res["dominant_colors"]
    assert res["bg_tone_distribution"]
    assert all(c in get_concepts() for c in res["suggested_concepts"])
    assert res["korean_words"] == []  # OCR 미구현 자리
    print(f"  ✓ 파이프라인(mock): {res['analyzed_count']}개 분석, 추천={res['suggested_concepts']}")


def test_max_items_clamped():
    # 21개 요청해도 HARD_MAX_ITEMS 이하로 제한, 음수 방어
    many = "".join(
        f'<li class="search-product"><img class="search-product-wrap-img" data-img-src="https://img/{i}.jpg"></li>'
        for i in range(30)
    )
    html = f'<ul id="productList">{many}</ul>'
    res = analyze_competitor(
        "https://www.coupang.com/np/search?q=x",
        max_items=999,
        respect_robots=False,
        html_fetcher=lambda u: html,
        image_fetcher=lambda u: _png_bytes((100, 150, 200)),
    )
    assert res["analyzed_count"] <= HARD_MAX_ITEMS
    print(f"  ✓ max_items 상한 제한: {res['analyzed_count']} <= {HARD_MAX_ITEMS}")


# ───────── 캐시 ─────────

def test_cache_roundtrip(tmp_path=None):
    path = Path(tmp_path) / "c.json" if tmp_path else ROOT / "workspace" / "temp" / "_test_cache.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    url = "https://www.coupang.com/np/search?q=cache"
    payload = {"analyzed_count": 3, "suggested_concepts": ["coupang_sales"]}

    assert comp_cache.get_cached(url, cache_path=path) is None  # 처음엔 없음
    comp_cache.set_cached(url, payload, cache_path=path)
    got = comp_cache.get_cached(url, cache_path=path)
    assert got == payload

    # TTL 만료 (now 를 미래로)
    future = time.time() + comp_cache.TTL_SECONDS + 10
    assert comp_cache.get_cached(url, cache_path=path, now=future) is None
    print("  ✓ 캐시 저장/조회/만료 동작")


def test_cache_key_differs():
    assert comp_cache.url_key("https://a.com/x") != comp_cache.url_key("https://a.com/y")
    print("  ✓ URL별 캐시 키 구분")


# ───────── API 라우트 (TestClient, 네트워크 없음) ─────────

def test_api_bad_url():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    r = client.post("/api/analyze/competitor", json={"url": "ftp://nope"})
    assert r.status_code == 400
    print("  ✓ API: 잘못된 URL → 400")


def test_api_cache_hit_no_network():
    """캐시를 미리 채워두면 라우트가 네트워크 없이 캐시를 반환한다."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    url = "https://www.coupang.com/np/search?q=__apitest__"
    payload = {
        "analyzed_count": 2,
        "suggested_concepts": ["coupang_sales"],
        "dominant_colors": [], "bg_tone_distribution": {},
        "badge_ratio": 0.0, "avg_text_area_ratio": 0.0,
    }
    comp_cache.set_cached(url, payload)  # 기본 캐시 경로
    try:
        r = client.post("/api/analyze/competitor", json={"url": url})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["cached"] is True
        assert body["analyzed_count"] == 2
        print("  ✓ API: 캐시 적중 시 네트워크 없이 반환")
    finally:
        # 테스트 캐시 정리
        path = comp_cache._default_cache_path()
        if path.exists():
            import json
            data = json.loads(path.read_text(encoding="utf-8"))
            data.pop(comp_cache.url_key(url), None)
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ───────── 실제 호출 (옵트인) ─────────

def test_live_coupang_optional():
    if os.environ.get("RUN_LIVE_TESTS") != "true":
        print("  · (skip) 실제 쿠팡 호출은 RUN_LIVE_TESTS=true 일 때만")
        return
    url = "https://www.coupang.com/np/search?q=텀블러"
    try:
        res = analyze_competitor(url, max_items=5)
        print(f"  ✓ LIVE: 발견 {res['thumbnails_found']}, 분석 {res['analyzed_count']}, 추천 {res.get('suggested_concepts')}")
    except RobotsBlockedError as e:
        print(f"  · LIVE robots 차단(정상 동작): {e}")


if __name__ == "__main__":
    print("\n=== 경쟁사 분석 테스트 ===")
    test_parse_thumbnail_urls()
    test_parse_empty_html()
    test_quantize_dominant_colors()
    test_classify_bg_tone()
    test_estimate_text_area_ratio()
    test_detect_discount_badge()
    test_suggest_concepts_are_real()
    test_aggregate_empty()
    test_robots_disallow_and_allow()
    test_analyze_blocked_raises()
    test_analyze_competitor_with_mocks()
    test_max_items_clamped()
    test_cache_roundtrip()
    test_cache_key_differs()
    test_api_bad_url()
    test_api_cache_hit_no_network()
    test_live_coupang_optional()
    print("\n✅ 경쟁사 분석 테스트 전체 통과")
