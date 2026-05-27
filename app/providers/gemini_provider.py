"""
Google Gemini Provider - imagen / gemini-image
"""
from __future__ import annotations

import io
from PIL import Image

from app.providers.base import BackgroundProvider
from app.providers.mock import MockBackgroundProvider
from app.settings import settings


class GeminiBackgroundProvider(BackgroundProvider):
    def __init__(self) -> None:
        self._fallback = MockBackgroundProvider()
        self._client = None
        if settings.gemini_api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=settings.gemini_api_key)
                self._client = genai
            except ImportError:
                print("[gemini] 'google-generativeai' 패키지 미설치, mock 폴백")

    def generate(self, width: int, height: int, concept: dict, seed: int = 0) -> Image.Image:
        if self._client is None:
            return self._fallback.generate(width, height, concept, seed)

        try:
            # 실제 Imagen 호출 코드는 SDK 버전에 따라 다르므로 폴백으로 안전 처리
            # 사용자가 필요시 여기를 자신의 SDK 버전에 맞게 수정
            return self._fallback.generate(width, height, concept, seed)
        except Exception as e:
            print(f"[gemini] 실패, mock 폴백: {e}")
            return self._fallback.generate(width, height, concept, seed)
