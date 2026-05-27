"""
Pydantic 스키마 - API I/O 타입 정의
"""
from typing import Optional, List
from pydantic import BaseModel, Field


# ===== 업로드 응답 =====

class UploadResponse(BaseModel):
    upload_id: str
    filename: str
    width: int
    height: int
    has_alpha: bool
    detected_category: Optional[str] = None
    suggested_concepts: List[str] = Field(default_factory=list)
    quality_warnings: List[str] = Field(default_factory=list)


# ===== 생성 요청 =====

class TextOption(BaseModel):
    """문구 옵션 - 사용자가 비워두면 AI가 추천"""
    headline: Optional[str] = None
    sub_text: Optional[str] = None
    badge: Optional[str] = None
    discount_percent: Optional[int] = None


class ProductInfo(BaseModel):
    """제품 정보 - 라이프스타일 신 생성 + 카테고리별 배치에 사용"""
    product_name: Optional[str] = None
    brand_name: Optional[str] = None
    category: str = "기타"          # 가구/의류/식품/전자제품/뷰티/생활용품/액세서리/기타
    sub_category: Optional[str] = None
    size_w: Optional[float] = None  # 가로 cm
    size_h: Optional[float] = None  # 세로 cm
    size_d: Optional[float] = None  # 깊이 cm
    size_label: Optional[str] = None  # S/M/L (사이즈 모를 때 대체)
    material: Optional[str] = None
    color: Optional[str] = None
    use_space: Optional[str] = None  # 거실/침실/주방/욕실/사무실/야외/공용
    target_audience: Optional[str] = None
    mood_keywords: Optional[List[str]] = None

    def cache_signature(self) -> str:
        """프롬프트 캐시 키용 안정 문자열 (None 은 빈값)."""
        parts = [
            self.category or "", self.sub_category or "", self.material or "",
            self.color or "", self.use_space or "",
            ",".join(self.mood_keywords or []),
        ]
        return "|".join(parts)


class GenerateRequest(BaseModel):
    upload_id: str
    concept: str = "white_minimal"
    platform: str = "coupang"
    variants: int = 1                  # 기본 1장 (비용 절약, 더만들기 버튼으로 추가)
    text: TextOption = Field(default_factory=TextOption)
    category_hint: Optional[str] = None
    keep_product_intact: bool = True  # 핵심 원칙: 제품 원본 훼손 금지
    brand_id: Optional[str] = None    # 브랜드 프리셋 적용 (컬러/로고/폰트)
    product_info: Optional[ProductInfo] = None  # 라이프스타일 신 생성용
    reference_id: Optional[str] = None  # 레퍼런스 이미지 분석 결과 적용
    fresh: bool = False                # 프롬프트/배경 캐시 무시


# ===== 생성 응답 =====

class Variant(BaseModel):
    variant_id: str
    file_url: str
    file_path: str
    width: int
    height: int
    ctr_score: int = Field(ge=0, le=100)
    qc_passed: bool
    qc_notes: List[str] = Field(default_factory=list)
    layout_used: str
    seed: int


class GenerateResponse(BaseModel):
    job_id: str
    concept: str
    platform: str
    variants: List[Variant]
    elapsed_ms: int


# ===== 검수 결과 =====

class QCReport(BaseModel):
    passed: bool
    notes: List[str]
    text_legibility: int = Field(ge=0, le=100)
    product_integrity: int = Field(ge=0, le=100)
    contrast_score: int = Field(ge=0, le=100)
    platform_compliance: bool
