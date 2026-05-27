"""
OpenAI Provider - 키 없으면 import 시점에 raise 하지 않고
                  실제 호출 시점에 mock으로 폴백
"""
from __future__ import annotations

import base64
import io
import os
from typing import List, Optional

from PIL import Image

from app.providers import llm_cache
from app.providers.base import BackgroundProvider, TextSuggestionProvider
from app.providers.llm_support import (
    MAX_TOKENS,
    build_system_prompt,
    build_user_prompt,
    gather_forbidden,
    generate_with_validation,
)
from app.providers.mock import MockBackgroundProvider, MockTextSuggestionProvider
from app.settings import settings


class OpenAIBackgroundProvider(BackgroundProvider):
    """DALL-E 3 로 라이프스타일 배경 생성 (Stability 폴백 경로로도 쓰임)"""

    _EST_COST_USD = 0.04  # dall-e-3 standard 1024 (~50원)

    def __init__(self) -> None:
        self._fallback = MockBackgroundProvider()
        self._client = None
        if settings.openai_api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=settings.openai_api_key)
            except ImportError:
                print("[openai] 'openai' 패키지 미설치, mock 폴백")

    def generate(self, width: int, height: int, concept: dict, seed: int = 0,
                 prompt: Optional[tuple] = None) -> Image.Image:
        import logging
        logger = logging.getLogger("thumbforge")
        if self._client is None:
            return self._fallback.generate(width, height, concept, seed)

        try:
            if prompt and prompt[0]:
                # DALL-E 는 negative prompt 미지원 → positive 에 제외 지시를 자연어로 포함
                neg = prompt[1] or ""
                text = (f"{prompt[0]}. Important: this is an empty background scene only, "
                        f"do NOT include any product, item, person, text, or logo. Avoid: {neg}")
            else:
                kw = concept.get("prompt_keywords", "minimal product background")
                text = (f"professional e-commerce product photography background only, "
                        f"NO product, NO text, NO logo. {kw}. clean composition, studio lighting, 4k")
            result = self._client.images.generate(
                model="dall-e-3",
                prompt=text[:3900],   # DALL-E 프롬프트 길이 제한 대비
                size="1024x1024",
                quality="standard",   # hd 는 비용 2배 → standard 고정
                n=1,
                response_format="b64_json",
            )
            b64 = result.data[0].b64_json
            img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
            logger.info("[openai] DALL-E 3 배경 생성 성공 비용=~$%.4f", self._EST_COST_USD)
            return img.resize((width, height), Image.LANCZOS)
        except Exception as e:
            logger.warning("[openai] 배경 생성 실패, mock 폴백: %s", e)
            return self._fallback.generate(width, height, concept, seed)


# 기본 문구 추천 모델. OPENAI_MODEL 로 오버라이드(레거시 OPENAI_TEXT_MODEL 도 인정).
_DEFAULT_TEXT_MODEL = (
    os.getenv("OPENAI_MODEL") or os.getenv("OPENAI_TEXT_MODEL") or "gpt-4o-mini"
)


class OpenAITextSuggestionProvider(TextSuggestionProvider):
    """
    실제 LLM(OpenAI Chat) 기반 매출형 문구 추천.

    설계 원칙
    ─ OPENAI_API_KEY 가 있을 때만 실제 호출, 없으면 mock 폴백
    ─ 모델: gpt-4o-mini 기본, OPENAI_MODEL 로 변경 / max_tokens=300
    ─ response_format={"type":"json_object"} 로 JSON 강제
    ─ 카테고리/컨셉/플랫폼 금지어 + 컨셉 톤 가이드를 system 에 주입
    ─ 검증 레이어(누락 채움/길이 잘라내기/금지어 1회 재호출)는 llm_support 공유
    ─ (provider,model,category,concept,platform) 캐시 + 사용량 기록
    ─ 호출/파싱 실패 시 예외로 죽지 않고 mock 폴백
    """

    def __init__(self) -> None:
        self._fallback = MockTextSuggestionProvider()
        self._client = None
        self._model = _DEFAULT_TEXT_MODEL
        if settings.openai_api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=settings.openai_api_key)
            except ImportError:
                print("[openai] 'openai' 패키지 미설치, 문구 추천 mock 폴백")

    # ───────── 금지어 수집 (공유 로직 위임) ─────────

    def _gather_forbidden(
        self, category: str, concept: str, platform: Optional[str] = None
    ) -> List[str]:
        return gather_forbidden(category, concept, platform)

    def _build_messages(
        self,
        category: str,
        concept: str,
        product_hint: Optional[str] = None,
        platform: Optional[str] = None,
        strict: bool = False,
        forbidden_hits: Optional[List[str]] = None,
    ) -> list[dict]:
        forbidden = self._gather_forbidden(category, concept, platform)
        system = build_system_prompt(
            category, concept, platform, forbidden,
            strict=strict, forbidden_hits=forbidden_hits,
        )
        user = build_user_prompt(category, concept, platform, product_hint)
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def suggest(
        self,
        category: str,
        concept: str,
        product_hint: Optional[str] = None,
        platform: Optional[str] = None,
        *,
        fresh: bool = False,
        use_cache: bool = False,
    ) -> dict:
        if self._client is None:
            # 키 없음/패키지 없음 → mock 폴백
            return self._fallback.suggest(category, concept, product_hint)

        if use_cache and not fresh:
            cached = llm_cache.get("openai", self._model, category, concept, platform)
            if cached is not None:
                from app.providers import llm_usage
                llm_usage.record("openai", self._model, 0, 0, cached=True)
                return cached

        def _complete(strict: bool, hits: Optional[List[str]]):
            messages = self._build_messages(
                category, concept, product_hint, platform,
                strict=strict, forbidden_hits=hits,
            )
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.8,
                max_tokens=MAX_TOKENS,
            )
            content = resp.choices[0].message.content
            usage = getattr(resp, "usage", None)
            ptok = int(getattr(usage, "prompt_tokens", 0) or 0)
            ctok = int(getattr(usage, "completion_tokens", 0) or 0)
            return content, ptok, ctok

        forbidden = self._gather_forbidden(category, concept, platform)
        fill = self._fallback.suggest("general", "general")
        result = generate_with_validation(
            complete=_complete, forbidden=forbidden, fill=fill,
            provider_name="openai", model=self._model,
        )
        if result is None:
            return self._fallback.suggest(category, concept, product_hint)
        if use_cache:
            llm_cache.set("openai", self._model, category, concept, platform, result)
        return result
