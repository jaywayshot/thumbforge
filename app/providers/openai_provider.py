"""
OpenAI Provider - 키 없으면 import 시점에 raise 하지 않고
                  실제 호출 시점에 mock으로 폴백
"""
from __future__ import annotations

import base64
import io
from typing import Optional

from PIL import Image

from app.providers.base import BackgroundProvider
from app.providers.mock import MockBackgroundProvider
from app.settings import settings


class OpenAIBackgroundProvider(BackgroundProvider):
    """gpt-image-1 / DALL-E 3로 배경 생성"""

    def __init__(self) -> None:
        self._fallback = MockBackgroundProvider()
        self._client = None
        if settings.openai_api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=settings.openai_api_key)
            except ImportError:
                print("[openai] 'openai' 패키지 미설치, mock 폴백")

    def generate(self, width: int, height: int, concept: dict, seed: int = 0) -> Image.Image:
        if self._client is None:
            return self._fallback.generate(width, height, concept, seed)

        try:
            prompt_kw = concept.get("prompt_keywords", "minimal product background")
            prompt = (
                f"professional e-commerce product photography background only, "
                f"NO product, NO text, NO logo. {prompt_kw}. "
                f"clean composition, studio lighting, 4k"
            )
            # gpt-image-1은 1024x1024 / 1536x1024 / 1024x1536만 지원
            size = "1024x1024"
            result = self._client.images.generate(
                model="gpt-image-1",
                prompt=prompt,
                size=size,
                n=1,
            )
            b64 = result.data[0].b64_json
            img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
            return img.resize((width, height), Image.LANCZOS)
        except Exception as e:
            print(f"[openai] 배경 생성 실패, mock 폴백: {e}")
            return self._fallback.generate(width, height, concept, seed)
