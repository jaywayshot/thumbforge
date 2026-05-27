"""
경쟁사 썸네일 분석 (쿠팡 검색결과 정적 HTML 파싱 전용)

핵심 원칙
─ robots.txt 존중: 차단되어 있으면 호출하지 않고 정직하게 알린다.
─ 헤드리스 브라우저 없음: 정적 HTML 만 파싱(httpx + BeautifulSoup).
─ 한 사이트에 부하를 주지 않도록 순차 처리 + 최대 20개 제한.
─ OCR 미구현: 한글 단어 빈도는 추후 항목으로 빈 값만 반환.

분석 항목
─ dominant 컬러 (Pillow median-cut 양자화 빈도 기반)
─ 배경 톤 (밝음/어두움 × 유채/무채)
─ 텍스트 영역 비율 (엣지 밀도 추정 — 텍스트 픽셀 근사)
─ 할인 뱃지 유무 (강한 빨강 영역 휴리스틱)
─ suggested_concepts: 위 결과로 실제 컨셉 ID 추천
"""
from __future__ import annotations

import io
import time
from typing import Callable, Dict, List, Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import numpy as np
from PIL import Image, ImageFilter

from app.analyzers.sites import detect_adapter
from app.services.concept_loader import get_concepts

# ───────── 상수 ─────────

# 정직한 User-Agent (봇임을 숨기지 않는다)
USER_AGENT = (
    "ThumbForge-CompetitorAnalyzer/1.0 "
    "(+https://github.com/jaywayshot/thumbforge)"
)
HARD_MAX_ITEMS = 20            # 한 번에 최대 20개 (부하 방지)
DEFAULT_MAX_ITEMS = 20
REQUEST_TIMEOUT = 10.0         # 초
POLITE_DELAY = 0.3             # 이미지 순차 다운로드 간 최소 간격(초)

# 타입 별칭: 테스트에서 네트워크를 주입(mock)하기 위한 후크
HtmlFetcher = Callable[[str], str]
ImageFetcher = Callable[[str], bytes]


class RobotsBlockedError(Exception):
    """robots.txt 가 해당 URL 수집을 금지함."""


# ───────── robots.txt ─────────

def is_allowed_by_robots(
    url: str,
    user_agent: str = USER_AGENT,
    *,
    robots_text: Optional[str] = None,
) -> bool:
    """
    robots.txt 규칙상 url 수집이 허용되는지.
    robots_text 를 주면 그것으로 판정(테스트용), 아니면 사이트에서 가져온다.
    가져오기 실패 시 보수적으로 '허용'으로 본다(쿠팡 robots 가 막으면 막힌 그대로 반영됨).
    """
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = RobotFileParser()
    rp.set_url(robots_url)

    if robots_text is not None:
        rp.parse(robots_text.splitlines())
    else:
        try:
            import httpx

            resp = httpx.get(
                robots_url,
                headers={"User-Agent": user_agent},
                timeout=REQUEST_TIMEOUT,
                follow_redirects=True,
            )
            if resp.status_code >= 400:
                # robots.txt 가 없으면 관례상 전부 허용
                return True
            rp.parse(resp.text.splitlines())
        except Exception:
            return True

    return rp.can_fetch(user_agent, url)


# ───────── HTML 파싱: 썸네일 URL 추출 (사이트 어댑터 위임) ─────────

def parse_thumbnail_urls(html: str, base_url: str) -> List[str]:
    """
    base_url 도메인으로 사이트를 감지해 해당 어댑터의 추출 규칙을 적용한다.
    (쿠팡/11번가/네이버쇼핑/제네릭 — app/analyzers/sites.py)
    """
    return detect_adapter(base_url).parse_thumbnail_urls(html, base_url)


# ───────── 단일 이미지 분석 ─────────

def _to_rgb_array(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGB"), dtype=np.uint8)


def quantize_dominant_colors(img: Image.Image, k: int = 5) -> List[Dict]:
    """median-cut 양자화로 dominant 컬러 k개 추출. 빈도 내림차순."""
    small = img.convert("RGB").resize((96, 96))
    q = small.quantize(colors=k, method=Image.Quantize.MEDIANCUT)
    palette = q.getpalette() or []
    color_counts = q.getcolors() or []  # [(count, palette_index), ...]
    total = sum(c for c, _ in color_counts) or 1

    out: List[Dict] = []
    for count, idx in sorted(color_counts, key=lambda x: x[0], reverse=True):
        r, g, b = palette[idx * 3 : idx * 3 + 3]
        out.append(
            {
                "hex": f"#{r:02X}{g:02X}{b:02X}",
                "rgb": [int(r), int(g), int(b)],
                "ratio": round(count / total, 4),
            }
        )
    return out


def _border_pixels(arr: np.ndarray, band: int = 6) -> np.ndarray:
    """이미지 테두리 픽셀(배경 추정용)을 모은 (N,3) 배열."""
    top = arr[:band, :, :].reshape(-1, 3)
    bottom = arr[-band:, :, :].reshape(-1, 3)
    left = arr[:, :band, :].reshape(-1, 3)
    right = arr[:, -band:, :].reshape(-1, 3)
    return np.concatenate([top, bottom, left, right], axis=0)


def classify_bg_tone(img: Image.Image) -> Dict[str, str]:
    """테두리 픽셀로 배경 톤 판정: 밝음/어두움 × 유채/무채."""
    arr = _to_rgb_array(img)
    border = _border_pixels(arr).astype(np.float32)
    # 밝기 (Rec.601 luma)
    luma = border @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    brightness = "밝음" if float(luma.mean()) >= 140 else "어두움"
    # 채도 (max-min) 평균
    chroma_val = float((border.max(axis=1) - border.min(axis=1)).mean())
    chroma = "유채" if chroma_val >= 28 else "무채"
    return {
        "brightness": brightness,
        "chroma": chroma,
        "label": f"{brightness}/{chroma}",
    }


def estimate_text_area_ratio(img: Image.Image) -> float:
    """
    엣지 밀도로 텍스트 영역 비율을 근사한다.
    텍스트는 작고 날카로운 엣지가 밀집 → FIND_EDGES 후 강한 엣지 픽셀 비율.
    (제품 윤곽도 일부 잡히는 근사치임을 전제)
    """
    gray = img.convert("L").resize((200, 200))
    edges = gray.filter(ImageFilter.FIND_EDGES)
    e = np.asarray(edges, dtype=np.uint8)
    # FIND_EDGES 는 이미지 경계에 1px 인공 엣지를 남기므로 테두리를 잘라낸다.
    e = e[2:-2, 2:-2]
    strong = np.count_nonzero(e > 60)
    return round(strong / e.size, 4)


def detect_discount_badge(img: Image.Image) -> Dict:
    """
    강한 빨강 영역 비율로 할인 뱃지(빨간 원형/별형) 유무를 휴리스틱 판정.
    R 이 충분히 크고 G,B 가 낮은 채도 높은 빨강 픽셀 비율 기준.
    """
    arr = _to_rgb_array(img).astype(np.int16)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    strong_red = (r > 150) & (g < 90) & (b < 90) & ((r - np.maximum(g, b)) > 70)
    red_ratio = float(np.count_nonzero(strong_red) / strong_red.size)
    return {"has_badge": red_ratio >= 0.012, "red_ratio": round(red_ratio, 4)}


def analyze_single_image(img: Image.Image) -> Dict:
    """단일 썸네일에 대한 모든 지표."""
    return {
        "dominant_colors": quantize_dominant_colors(img, k=5),
        "bg_tone": classify_bg_tone(img),
        "text_area_ratio": estimate_text_area_ratio(img),
        "badge": detect_discount_badge(img),
    }


# ───────── 집계 ─────────

def _is_reddish(rgb: List[int]) -> bool:
    r, g, b = rgb
    return r > 150 and (r - max(g, b)) > 50


def aggregate_results(items: List[Dict]) -> Dict:
    """이미지별 분석 결과를 전체 통계로 집계."""
    n = len(items)
    if n == 0:
        return {
            "analyzed_count": 0,
            "dominant_colors": [],
            "bg_tone_distribution": {},
            "badge_ratio": 0.0,
            "avg_text_area_ratio": 0.0,
        }

    # dominant 컬러: 각 이미지의 컬러를 비율 가중치로 누적 → hex 빈도 상위
    color_weight: Dict[str, float] = {}
    color_rgb: Dict[str, List[int]] = {}
    for it in items:
        for c in it["dominant_colors"]:
            color_weight[c["hex"]] = color_weight.get(c["hex"], 0.0) + c["ratio"]
            color_rgb[c["hex"]] = c["rgb"]
    top_colors = sorted(color_weight.items(), key=lambda x: x[1], reverse=True)[:8]
    total_w = sum(w for _, w in top_colors) or 1.0
    dominant_colors = [
        {"hex": hx, "rgb": color_rgb[hx], "weight": round(w / total_w, 4)}
        for hx, w in top_colors
    ]

    # 배경 톤 분포
    tone_dist: Dict[str, int] = {}
    for it in items:
        label = it["bg_tone"]["label"]
        tone_dist[label] = tone_dist.get(label, 0) + 1

    badge_ratio = sum(1 for it in items if it["badge"]["has_badge"]) / n
    avg_text = sum(it["text_area_ratio"] for it in items) / n

    return {
        "analyzed_count": n,
        "dominant_colors": dominant_colors,
        "bg_tone_distribution": tone_dist,
        "badge_ratio": round(badge_ratio, 4),
        "avg_text_area_ratio": round(avg_text, 4),
    }


# ───────── 컨셉 추천 ─────────

def suggest_concepts_from_analysis(agg: Dict) -> List[str]:
    """
    집계 결과 → 적합한 컨셉 ID 추천.
    실제 존재하는 컨셉만 반환(없으면 제외). 최대 4개.
    """
    available = set(get_concepts().keys())
    scores: Dict[str, float] = {}

    def bump(cid: str, pts: float) -> None:
        if cid in available:
            scores[cid] = scores.get(cid, 0.0) + pts

    tone = agg.get("bg_tone_distribution", {})
    total_tone = sum(tone.values()) or 1
    dark = sum(v for k, v in tone.items() if k.startswith("어두움")) / total_tone
    light = sum(v for k, v in tone.items() if k.startswith("밝음")) / total_tone
    chromatic = sum(v for k, v in tone.items() if k.endswith("유채")) / total_tone

    badge_ratio = agg.get("badge_ratio", 0.0)
    text_ratio = agg.get("avg_text_area_ratio", 0.0)
    reddish_dom = any(_is_reddish(c["rgb"]) for c in agg.get("dominant_colors", [])[:4])

    # 빨강 우세 + 할인 뱃지 多 → 쿠팡 판매형 / 할인행사형
    if reddish_dom or badge_ratio >= 0.4:
        bump("coupang_sales", 2.0 + badge_ratio)
        bump("discount_event", 1.5 + badge_ratio)
    # 어두운 배경 → 프리미엄/블랙 럭셔리
    if dark >= 0.4:
        bump("premium_luxury", 1.5 + dark)
        bump("black_luxury", 1.0 + dark)
    # 밝고 무채(흰 배경) → 화이트 미니멀 / 애플 스타일
    if light >= 0.5 and chromatic < 0.5:
        bump("white_minimal", 1.5 + light)
        bump("apple_style", 1.0)
    # 밝고 유채(파스텔/감성) → 스마트스토어 감성형
    if light >= 0.5 and chromatic >= 0.5:
        bump("smartstore_emotional", 1.2 + chromatic)
    # 텍스트 비중이 큼 → 홈쇼핑형(거대 문구)
    if text_ratio >= 0.15:
        bump("homeshopping", 1.0 + text_ratio)

    ranked = [cid for cid, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)]
    if not ranked:
        # 분석 신호가 약하면 흔한 기본값 (존재하는 것만)
        ranked = [c for c in ("coupang_sales", "white_minimal") if c in available]
    return ranked[:4]


# ───────── 네트워크 기본 구현 ─────────

def _default_html_fetcher(url: str) -> str:
    import httpx

    resp = httpx.get(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "ko-KR,ko;q=0.9",
        },
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.text


def _default_image_fetcher(url: str) -> bytes:
    import httpx

    resp = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.content


# ───────── 오케스트레이터 ─────────

def analyze_competitor(
    url: str,
    max_items: int = DEFAULT_MAX_ITEMS,
    *,
    respect_robots: bool = True,
    html_fetcher: Optional[HtmlFetcher] = None,
    image_fetcher: Optional[ImageFetcher] = None,
    robots_text: Optional[str] = None,
) -> Dict:
    """
    검색결과 URL(쿠팡/11번가/네이버쇼핑/제네릭) → 상위 N개 썸네일 분석 결과.
    URL 도메인으로 사이트 어댑터를 자동 감지한다.
    네트워크 후크(html_fetcher/image_fetcher)는 테스트에서 주입 가능.
    동기 함수 — async 라우트에서는 run_in_threadpool 로 호출.
    """
    max_items = max(1, min(int(max_items), HARD_MAX_ITEMS))
    adapter = detect_adapter(url)

    if respect_robots and not is_allowed_by_robots(url, robots_text=robots_text):
        raise RobotsBlockedError(
            f"robots.txt 규칙상 해당 URL({adapter.label}) 수집이 금지되어 있습니다. 분석을 중단했습니다."
        )

    fetch_html = html_fetcher or _default_html_fetcher
    fetch_image = image_fetcher or _default_image_fetcher

    html = fetch_html(url)
    thumb_urls = adapter.parse_thumbnail_urls(html, base_url=url)[:max_items]

    items: List[Dict] = []
    failed = 0
    for i, turl in enumerate(thumb_urls):
        try:
            data = fetch_image(turl)
            img = Image.open(io.BytesIO(data))
            img.load()
            items.append(analyze_single_image(img))
        except Exception:
            failed += 1
        # 순차 처리 + 예의상 간격 (마지막 항목 뒤에는 생략)
        if image_fetcher is None and i < len(thumb_urls) - 1:
            time.sleep(POLITE_DELAY)

    agg = aggregate_results(items)
    agg["suggested_concepts"] = suggest_concepts_from_analysis(agg)
    agg["source_url"] = url
    agg["site"] = adapter.name
    agg["site_label"] = adapter.label
    agg["thumbnails_found"] = len(thumb_urls)
    agg["fetch_failed"] = failed
    # OCR 미구현 — 추후 표시용 자리만 둔다
    agg["korean_words"] = []
    agg["korean_words_note"] = "OCR 미구현 — 한글 단어 빈도는 추후 지원 예정"
    return agg
