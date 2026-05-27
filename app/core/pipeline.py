"""
메인 파이프라인 - 업로드 ID 받아 N개 variant 생성
"""
from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Optional

from PIL import Image

from app.core import matting
from app.core.composer import compose_thumbnail
from app.core.layout import build_layout, variants_for
from app.core.qc import estimate_ctr_score, validate_text
from app.models.schemas import GenerateRequest, GenerateResponse, Variant
from app.providers.factory import (
    get_background_provider,
    get_qc_provider,
    get_text_provider,
)
from app.services.brand_store import (
    apply_brand_to_concept,
    get_brand,
    get_brand_asset_path,
)
from app.services.concept_loader import (
    check_forbidden_words,
    detect_category_by_filename,
    get_concept,
    get_platform,
)
from app.services import job_store
from app.services.storage import find_upload, job_output_dir, new_job_id, open_image
from app.settings import settings


def _final_size_for(platform_name: str) -> tuple[int, int]:
    p = get_platform(platform_name)
    sizes = p.get("sizes", {})
    if "thumbnail" in sizes:
        return tuple(sizes["thumbnail"])
    return (settings.output_size, settings.output_size)


def run_generation(req: GenerateRequest) -> GenerateResponse:
    t0 = time.time()

    # 1. 업로드 찾기
    upload_path = find_upload(req.upload_id)
    if upload_path is None:
        raise FileNotFoundError(f"upload_id={req.upload_id} 의 업로드 파일을 찾을 수 없습니다")

    # 2. 누끼
    original = open_image(upload_path)
    product_rgba = matting.remove_background(original)
    product_rgba = matting.crop_to_content(product_rgba, padding=10)

    # 3. 컨셉/플랫폼
    concept = get_concept(req.concept)
    width, height = _final_size_for(req.platform)

    # 3-1. 브랜드 프리셋 적용 (있으면)
    brand = get_brand(req.brand_id) if req.brand_id else None
    if brand:
        concept = apply_brand_to_concept(concept, brand)
    brand_logo_path = get_brand_asset_path(brand.brand_id, brand.logo_filename) if (brand and brand.logo_filename) else None
    brand_font_path = get_brand_asset_path(brand.brand_id, brand.font_filename) if (brand and brand.font_filename) else None

    # 4. variants 생성용 레이아웃 후보
    base_layout = concept.get("layout", "center_product")
    layout_pool = variants_for(base_layout)

    # 5. 카테고리 / 문구 결정
    category = req.category_hint or detect_category_by_filename(upload_path.name)

    text_provider = get_text_provider()
    text_input = req.text

    # 브랜드 기본값 채우기
    if brand:
        if not text_input.headline and brand.default_headline:
            text_input.headline = brand.default_headline
        if not text_input.sub_text and brand.default_sub_text:
            text_input.sub_text = brand.default_sub_text
        if not text_input.badge and brand.default_badge:
            text_input.badge = brand.default_badge

    # 자동 추천 채우기 (사용자가 비워둔 칸만)
    suggested = None
    if not text_input.headline or not text_input.sub_text or not text_input.badge:
        suggested = text_provider.suggest(category=category, concept=req.concept)

    bg_provider = get_background_provider()
    qc_provider = get_qc_provider()

    # 6. variants 루프
    job_id = new_job_id()
    out_dir = job_output_dir(job_id)
    variants: list[Variant] = []
    variant_meta: dict[str, dict] = {}  # 피드백 복원용 (variant_id → 메타)

    for i in range(max(1, req.variants)):
        seed = random.randint(1, 10_000_000)
        layout_name = layout_pool[i % len(layout_pool)]
        layout = build_layout(layout_name, width, height)

        bg = bg_provider.generate(width, height, concept, seed=seed)

        # 매 variant마다 문구 살짝 다양화 (A/B 테스트)
        headline = text_input.headline
        if not headline and suggested:
            # 첫 추천 + 변형
            pool = [suggested["headline"]] + [f"{suggested['headline']} {n+1}" if False else suggested['headline'] for n in range(1)]
            headline = pool[0] if i == 0 else suggested["headline"]
        sub = text_input.sub_text or (suggested["sub_text"] if suggested else None)
        badge = text_input.badge or (suggested["badge"] if suggested else None)

        # 컨셉에 headline_max 제한
        headline_max = int(concept.get("headline_max", 14))
        if headline and len(headline) > headline_max:
            headline = headline[:headline_max].rstrip()

        composed = compose_thumbnail(
            background=bg,
            product_rgba=product_rgba,
            layout=layout,
            concept=concept,
            headline=headline,
            sub_text=sub,
            badge=badge,
            discount_percent=text_input.discount_percent,
            logo_path=brand_logo_path,
            font_path=brand_font_path,
        )

        # 검수
        qc_report = qc_provider.review(composed, meta={"platform": req.platform})
        # 금지문구 검사 (플랫폼 + 브랜드)
        forbidden, warnings_ = validate_text(headline, sub, req.platform)
        if brand and brand.forbidden_words:
            blob = " ".join(t for t in (headline, sub) if t)
            for w in brand.forbidden_words:
                if w and w in blob:
                    forbidden.append(w)
        notes = list(qc_report.get("notes", []))
        if forbidden:
            notes.append(f"플랫폼 금지문구 포함: {', '.join(forbidden)}")
            qc_report["passed"] = False
        if warnings_:
            notes.append(f"주의문구: {', '.join(warnings_)} (실제 사실인 경우만 사용)")

        ctr = estimate_ctr_score(
            composed,
            qc_report,
            has_discount=bool(text_input.discount_percent),
            has_badge=bool(badge),
        )

        # 저장
        variant_id = f"v{i+1}"
        out_path = out_dir / f"{variant_id}.png"
        composed.convert("RGBA").save(out_path, "PNG", optimize=True)

        variants.append(Variant(
            variant_id=variant_id,
            file_url=f"/files/{job_id}/{variant_id}.png",
            file_path=str(out_path),
            width=width,
            height=height,
            ctr_score=ctr,
            qc_passed=bool(qc_report.get("passed", True)) and not forbidden,
            qc_notes=notes,
            layout_used=layout_name,
            seed=seed,
        ))
        variant_meta[variant_id] = {
            "layout_used": layout_name,
            "headline": headline,
            "sub_text": sub,
            "badge": badge,
            "has_discount": bool(text_input.discount_percent),
            "ctr_estimate": ctr,
        }

    # CTR 높은 순으로 정렬
    variants.sort(key=lambda v: v.ctr_score, reverse=True)

    # 피드백 복원용 generation 메타데이터 영속화 (워크스페이스에만 저장)
    try:
        job_store.save_generation_meta(
            job_id,
            upload_id=req.upload_id,
            category=category,
            concept=req.concept,
            platform=req.platform,
            text_provider=(settings.text_provider or "mock").lower(),
            variants=variant_meta,
        )
    except Exception:
        pass  # 메타 저장 실패가 생성 자체를 막지 않도록

    elapsed = int((time.time() - t0) * 1000)
    return GenerateResponse(
        job_id=job_id,
        concept=req.concept,
        platform=req.platform,
        variants=variants,
        elapsed_ms=elapsed,
    )
