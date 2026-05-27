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


class GenerateRequest(BaseModel):
    upload_id: str
    concept: str = "white_minimal"
    platform: str = "coupang"
    variants: int = 4
    text: TextOption = Field(default_factory=TextOption)
    category_hint: Optional[str] = None
    keep_product_intact: bool = True  # 핵심 원칙: 제품 원본 훼손 금지
    brand_id: Optional[str] = None    # 브랜드 프리셋 적용 (컬러/로고/폰트)


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
