"""
사이트별 어댑터 (썸네일 URL 추출 규칙)

URL 도메인으로 사이트를 자동 감지해 해당 어댑터를 고른다.
각 어댑터는 그 사이트 검색결과 HTML 에서 상품 썸네일 img URL 을 뽑는
CSS 셀렉터와 이미지 CDN 힌트만 다르게 갖는다(이미지 분석 로직은 사이트 무관).

수집 가능성(2026-05 기준 정직한 User-Agent + 정적 HTML 한정):
─ coupang        : robots.txt/페이지 모두 403(Akamai) → 현재 차단
─ 11st           : robots 허용이나 검색결과가 JS(SPA)로 렌더 → 정적 HTML 에 상품 없음
─ naver shopping : robots.txt 가 Disallow: / (전면 금지) → 수집 금지(시도 안 함)

→ 어느 사이트가 추후 정적 HTML 을 제공하면 셀렉터만으로 즉시 동작한다.
"""
from __future__ import annotations

from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


class SiteAdapter:
    """사이트별 썸네일 추출 어댑터 기본 클래스."""

    name: str = "generic"
    label: str = "알 수 없는 사이트"
    domains: Tuple[str, ...] = ()
    selectors: Tuple[str, ...] = ()
    cdn_hints: Tuple[str, ...] = ()

    def matches(self, netloc: str) -> bool:
        return any(d in netloc for d in self.domains)

    def parse_thumbnail_urls(self, html: str, base_url: str) -> List[str]:
        soup = BeautifulSoup(html, "html.parser")
        urls: List[str] = []
        seen = set()

        def _push(raw: Optional[str]) -> None:
            if not raw:
                return
            raw = raw.strip()
            if not raw or raw.startswith("data:"):
                return
            full = urljoin(base_url, raw)
            if full not in seen:
                seen.add(full)
                urls.append(full)

        def _img_src(img) -> Optional[str]:
            # 지연 로딩(data-*) 우선, 없으면 src
            return (
                img.get("data-img-src")
                or img.get("data-src")
                or img.get("data-original")
                or img.get("src")
            )

        # 1순위: 사이트별 상품 이미지 셀렉터
        for sel in self.selectors:
            for img in soup.select(sel):
                _push(_img_src(img))

        # 2순위(폴백): 이미지 CDN 힌트 / thumbnail 키워드가 든 img
        if not urls:
            hints = self.cdn_hints + ("thumbnail",)
            for img in soup.find_all("img"):
                src = _img_src(img) or ""
                if any(h in src for h in hints):
                    _push(src)

        return urls


class CoupangAdapter(SiteAdapter):
    name = "coupang"
    label = "쿠팡"
    domains = ("coupang.com",)
    selectors = (
        "img.search-product-wrap-img",
        "li.search-product img",
        "ul#productList img",
        "#product-list img",
    )
    cdn_hints = ("coupangcdn.com",)


class ElevenStAdapter(SiteAdapter):
    name = "11st"
    label = "11번가"
    domains = ("11st.co.kr",)
    selectors = (
        "img.img_plot",
        ".c_card_item img",
        ".c_listing img",
        ".product_info img",
    )
    cdn_hints = ("011st.com", "11st.co.kr")


class NaverShoppingAdapter(SiteAdapter):
    name = "naver_shopping"
    label = "네이버 쇼핑"
    domains = ("shopping.naver.com",)
    selectors = (
        ".basicList_item img",
        ".product_item img",
        "img.thumbnail_thumb",
        ".basicList_link img",
    )
    cdn_hints = ("pstatic.net",)


class GenericAdapter(SiteAdapter):
    """알 수 없는 도메인 — thumbnail/image 키워드 휴리스틱만 사용."""

    name = "generic"
    label = "알 수 없는 사이트"
    selectors = ()
    cdn_hints = ("image",)


# 감지 우선순위 (구체적인 사이트 먼저)
_ADAPTERS: Tuple[SiteAdapter, ...] = (
    CoupangAdapter(),
    ElevenStAdapter(),
    NaverShoppingAdapter(),
)


def detect_adapter(url: str) -> SiteAdapter:
    """URL 도메인으로 사이트 어댑터를 고른다. 매칭 없으면 GenericAdapter."""
    netloc = urlparse(url).netloc.lower()
    for ad in _ADAPTERS:
        if ad.matches(netloc):
            return ad
    return GenericAdapter()


def supported_sites() -> List[dict]:
    """지원(인식) 사이트 목록 — UI/문서용."""
    return [{"name": a.name, "label": a.label, "domains": list(a.domains)} for a in _ADAPTERS]
