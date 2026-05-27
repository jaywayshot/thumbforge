"""
Provider 팩토리 - settings의 provider 이름으로 인스턴스 반환
모르는 이름이거나 키가 없으면 자동으로 mock 폴백
"""
from __future__ import annotations
from functools import lru_cache

from app.providers.base import BackgroundProvider, TextSuggestionProvider, QCProvider
from app.providers.mock import (
    MockBackgroundProvider,
    MockTextSuggestionProvider,
    MockQCProvider,
)
from app.settings import settings


@lru_cache(maxsize=1)
def get_background_provider() -> BackgroundProvider:
    name = (settings.bg_provider or "mock").lower()
    if name == "openai":
        from app.providers.openai_provider import OpenAIBackgroundProvider
        return OpenAIBackgroundProvider()
    if name == "stability":
        from app.providers.stability_provider import StabilityBackgroundProvider
        return StabilityBackgroundProvider()
    if name == "gemini":
        from app.providers.gemini_provider import GeminiBackgroundProvider
        return GeminiBackgroundProvider()
    return MockBackgroundProvider()


@lru_cache(maxsize=1)
def get_text_provider() -> TextSuggestionProvider:
    name = (settings.text_provider or "mock").lower()
    if name == "openai":
        # 키 없으면 OpenAITextSuggestionProvider 내부에서 자동 mock 폴백
        from app.providers.openai_provider import OpenAITextSuggestionProvider
        return OpenAITextSuggestionProvider()
    if name == "anthropic":
        from app.providers.anthropic_provider import AnthropicTextSuggestionProvider
        return AnthropicTextSuggestionProvider()
    return MockTextSuggestionProvider()


@lru_cache(maxsize=1)
def get_qc_provider() -> QCProvider:
    return MockQCProvider()
