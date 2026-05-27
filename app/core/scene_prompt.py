"""
라이프스타일 신(scene) 프롬프트 자동 생성기

ProductInfo + 컨셉 + 플랫폼 → (positive, negative) 영문 프롬프트.
핵심: 배경(환경)만 생성하고 제품 자체는 절대 생성하지 않는다(negative 로 차단).
누끼된 실제 제품은 이후 composer 가 합성한다.

Stability / DALL-E 모두 영문 프롬프트를 권장하므로, 한글 입력(공간/재질/색/무드)은
간단한 매핑으로 영문화한다(미등록 토큰은 그대로 전달).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.models.schemas import ProductInfo

# ───────── 카테고리별 신 템플릿 (영문) ─────────
# {use_space}, {color}, {mood} 치환
CATEGORY_SCENE: Dict[str, str] = {
    "가구": "spacious minimal {use_space} interior, {color} walls, wooden flooring, "
            "soft natural daylight from large window, {mood} atmosphere, empty staging area",
    "의류": "minimal clothing rack in {use_space}, white walls with line art posters, "
            "wooden floor, soft natural lighting, scandinavian style, {mood} atmosphere",
    "식품": "clean kitchen counter with marble surface, soft window light, minimal styling, "
            "natural ingredients in background, {mood} atmosphere",
    "전자제품": "minimal modern desk setup in {use_space}, white wall background, "
                "soft directional lighting, professional product shot environment, {mood}",
    "뷰티": "clean cosmetics shelf with marble background, soft pink and beige tones, "
            "delicate flowers, soft diffused lighting, {mood} atmosphere",
    "액세서리": "minimal display surface with neutral fabric, soft lighting, "
                "premium showcase environment, {mood} atmosphere",
    "생활용품": "minimal home setting in {use_space}, soft natural lighting, "
                "clean modern interior, {mood} atmosphere",
    "기타": "minimal clean studio environment, soft natural lighting, "
            "neutral background, {mood} atmosphere",
}
_DEFAULT_SCENE = CATEGORY_SCENE["기타"]

# ───────── 18개 컨셉별 무드 키워드 (영문) ─────────
CONCEPT_MOOD: Dict[str, List[str]] = {
    "coupang_sales": ["bright commercial", "vibrant", "energetic"],
    "smartstore_emotional": ["warm cozy", "lifestyle", "soft bokeh"],
    "premium_luxury": ["luxury", "elegant", "sophisticated lighting"],
    "black_luxury": ["dark luxury", "dramatic lighting", "metallic accents"],
    "white_minimal": ["minimalist", "clean", "lots of whitespace"],
    "tech_electronics": ["modern tech", "sleek", "clean futuristic"],
    "health_food": ["natural", "fresh", "organic healthy"],
    "female_emotional": ["soft feminine", "rose tones", "delicate"],
    "instagram_aesthetic": ["trendy", "film tone", "moody aesthetic"],
    "discount_event": ["vibrant", "bold", "promotional energetic"],
    "seasonal_event": ["festive", "warm tones", "celebratory"],
    "summer": ["fresh cool", "bright", "summery breezy"],
    "winter": ["cozy warm tones", "soft", "wintry calm"],
    "kids": ["playful colorful", "bright cheerful", "friendly"],
    "sports": ["dynamic", "energetic", "bold athletic"],
    "brand_shop": ["refined", "balanced", "premium"],
    "homeshopping": ["bright clear", "prominent", "vivid commercial"],
    "apple_style": ["ultra minimal", "clean premium", "lots of whitespace"],
}
_DEFAULT_MOOD = ["clean", "minimal", "professional"]

# ───────── 한글 → 영문 매핑 ─────────
_SPACE_EN = {
    "거실": "living room", "침실": "bedroom", "주방": "kitchen", "욕실": "bathroom",
    "서재": "study room", "사무실": "office", "야외": "outdoor", "공용": "neutral space",
}
_MATERIAL_EN = {
    "원목": "solid wood", "우드": "wood", "메탈": "metal", "메탈 프레임": "metal frame",
    "가죽": "leather", "패브릭": "fabric", "유리": "glass", "플라스틱": "plastic",
    "스테인리스": "stainless steel", "면": "cotton", "세라믹": "ceramic", "대리석": "marble",
}
_COLOR_EN = {
    "화이트": "white", "블랙": "black", "베이지": "beige", "그레이": "gray", "회색": "gray",
    "네이비": "navy", "브라운": "brown", "핑크": "pink", "그린": "green", "블루": "blue",
    "옐로": "yellow", "노랑": "yellow", "레드": "red", "빨강": "red", "아이보리": "ivory",
}
_MOOD_EN = {
    "미니멀": "minimalist", "북유럽": "scandinavian", "내추럴": "natural", "모던": "modern",
    "우드톤": "wood tone", "감성": "emotional warm", "럭셔리": "luxury", "빈티지": "vintage",
    "시크": "chic", "캐주얼": "casual", "클린": "clean", "프리미엄": "premium",
    "데일리": "daily casual", "건강": "healthy", "신선": "fresh", "따뜻한": "warm",
    "정갈한": "tidy", "깔끔한": "neat", "실용적": "practical", "로즈": "rose",
    "스칸디나비안": "scandinavian", "테크": "tech", "프로페셔널": "professional",
}


def _translate(token: str, table: Dict[str, str]) -> str:
    token = (token or "").strip()
    if not token:
        return ""
    return table.get(token, token)


def _translate_csv(value: Optional[str], table: Dict[str, str]) -> List[str]:
    """'화이트, 베이지' → ['white','beige']. 콤마/공백 분리."""
    if not value:
        return []
    out = []
    for part in value.replace("，", ",").split(","):
        t = _translate(part.strip(), table)
        if t:
            out.append(t)
    return out


# ───────── 메인 빌더 ─────────

def build_scene_prompt(
    product_info: Optional[ProductInfo],
    concept: dict,
    platform: str,
    reference: Optional[dict] = None,
    concept_id: Optional[str] = None,
) -> Tuple[str, str]:
    """(positive, negative) 영문 프롬프트 반환. concept_id 로 컨셉 무드 매핑."""
    pi = product_info or ProductInfo()
    category = pi.category or "기타"
    template = CATEGORY_SCENE.get(category, _DEFAULT_SCENE)

    # 공간/색/무드 영문화
    use_space = _translate(pi.use_space or "", _SPACE_EN) or "interior"
    colors = _translate_csv(pi.color, _COLOR_EN)
    color = colors[0] if colors else "neutral"

    moods = _translate_csv(",".join(pi.mood_keywords or []), _MOOD_EN)
    cid = concept_id or concept.get("_id") or ""
    concept_moods = CONCEPT_MOOD.get(cid, [])
    mood_all = moods + concept_moods
    mood_str = ", ".join(mood_all) if mood_all else "clean minimal"

    positive = template.format(use_space=use_space, color=color, mood=mood_str)

    # 재질감 반영
    materials = _translate_csv(pi.material, _MATERIAL_EN)
    if materials:
        positive += f", {', '.join(materials)} textures and accents"

    # 컨셉 prompt_keywords 보조 주입
    ckw = concept.get("prompt_keywords")
    if ckw:
        positive += f", {ckw}"

    # 레퍼런스 이미지 분석 반영(색/톤/무드)
    if reference:
        ref_colors = reference.get("dominant_colors_en") or reference.get("dominant_hex") or []
        if ref_colors:
            positive += f", color palette inspired by {', '.join(map(str, ref_colors[:3]))}"
        tone = reference.get("tone")
        if tone:
            positive += f", {tone} tone"
        ref_moods = reference.get("moods") or []
        if ref_moods:
            positive += f", {', '.join(ref_moods)}"

    positive += (
        ", interior photography, high quality, 4k, professional lighting, "
        "empty scene with space for a product, no product in frame"
    )

    # ───── negative: 제품/사람/마네킹/텍스트 등 차단 ─────
    negative_parts = [
        "product", "item", "foreground subject", "watermark", "text", "logo",
        "multiple objects", "blurry", "low quality", "distorted", "deformed",
        "person", "people", "human", "hands",
    ]
    if category == "의류":
        negative_parts += ["mannequin", "clothing on body", "model wearing"]
    if category == "가구":
        negative_parts += ["people sitting", "crowd"]
    negative = ", ".join(negative_parts)

    return positive, negative
