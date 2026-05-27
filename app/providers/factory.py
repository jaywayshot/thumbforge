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
    # 현재는 mock만 지원 (실제 LLM 어댑터 추가 자리)
    return MockTextSuggestionProvider()


@lru_cache(maxsize=1)
def get_qc_provider() -> QCProvider:
    return MockQCProvider()
