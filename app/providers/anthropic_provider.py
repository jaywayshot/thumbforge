"""
Anthropic(Claude) 문구 추천 Provider

설계 원칙 (OpenAI Provider 와 완전 대칭, 동일 검증 레이어 공유)
─ ANTHROPIC_API_KEY 가 있을 때만 실제 호출, 없으면 mock 폴백
─ 모델: claude-haiku-4-5 기본(저비용), ANTHROPIC_MODEL 로 변경 / max_tokens=300
─ system 프롬프트에 JSON 스키마 + 컨셉 톤 + 카테고리/컨셉/플랫폼 금지어 주입
─ 검증/누락보정/길이/금지어 1회 재호출/캐시/사용량은 llm_support·llm_cache 공유
─ anthropic 패키지는 선택적 의존성 (미설치 시 import 시점에 죽지 않음)
"""
from __future__ import annotations

import os
from typing import List, Optional

from app.providers import llm_cache
from app.providers.base import TextSuggestionProvider
from app.providers.llm_support import (
    MAX_TOKENS,
    build_system_prompt,
    build_user_prompt,
    gather_forbidden,
    generate_with_validation,
)
from app.providers.mock import MockTextSuggestionProvider
from app.settings import settings

# 기본 모델: 저비용 Haiku. ANTHROPIC_MODEL 로 오버라이드(레거시 ANTHROPIC_TEXT_MODEL 인정).
_DEFAULT_TEXT_MODEL = (
    os.getenv("ANTHROPIC_MODEL")
    or os.getenv("ANTHROPIC_TEXT_MODEL")
    or "claude-haiku-4-5"
)


def _gather_forbidden(category: str, concept: str) -> List[str]:
    """카테고리/컨셉/전 플랫폼 금지어 합집합 (모듈 레벨 — 기존 테스트 호환)."""
    return gather_forbidden(category, concept, None)


class AnthropicTextSuggestionProvider(TextSuggestionProvider):
    def __init__(self) -> None:
        self._fallback = MockTextSuggestionProvider()
        self._client = None
        self._model = _DEFAULT_TEXT_MODEL
        if settings.anthropic_api_key:
            try:
                from anthropic import Anthropic
                self._client = Anthropic(api_key=settings.anthropic_api_key)
            except ImportError:
                print("[anthropic] 'anthropic' 패키지 미설치, 문구 추천 mock 폴백")

    def _system_prompt(
        self,
        category: str,
        concept: str,
        platform: Optional[str] = None,
        strict: bool = False,
        forbidden_hits: Optional[List[str]] = None,
    ) -> str:
        forbidden = gather_forbidden(category, concept, platform)
        return build_system_prompt(
            category, concept, platform, forbidden,
            strict=strict, forbidden_hits=forbidden_hits,
        )

    @staticmethod
    def _extract_text(resp) -> str:
        """Anthropic messages 응답에서 텍스트 추출."""
        content = getattr(resp, "content", None)
        if not content:
            return ""
        parts = []
        for block in content:
            text = getattr(block, "text", None)
            if text is None and isinstance(block, dict):
                text = block.get("text")
            if text:
                parts.append(text)
        return "".join(parts)

    @staticmethod
    def _extract_usage(resp):
        u = getattr(resp, "usage", None)
        ptok = int(getattr(u, "input_tokens", 0) or 0)
        ctok = int(getattr(u, "output_tokens", 0) or 0)
        return ptok, ctok

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
            return self._fallback.suggest(category, concept, product_hint)

        if use_cache and not fresh:
            cached = llm_cache.get("anthropic", self._model, category, concept, platform)
            if cached is not None:
                from app.providers import llm_usage
                llm_usage.record("anthropic", self._model, 0, 0, cached=True)
                return cached

        def _complete(strict: bool, hits: Optional[List[str]]):
            system = self._system_prompt(
                category, concept, platform, strict=strict, forbidden_hits=hits
            )
            user = build_user_prompt(category, concept, platform, product_hint)
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            ptok, ctok = self._extract_usage(resp)
            return self._extract_text(resp), ptok, ctok

        forbidden = gather_forbidden(category, concept, platform)
        fill = self._fallback.suggest("general", "general")
        result = generate_with_validation(
            complete=_complete, forbidden=forbidden, fill=fill,
            provider_name="anthropic", model=self._model,
        )
        if result is None:
            return self._fallback.suggest(category, concept, product_hint)
        if use_cache:
            llm_cache.set("anthropic", self._model, category, concept, platform, result)
        return result
