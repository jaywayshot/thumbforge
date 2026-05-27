"""
Stability AI Provider - SD3 / SDXL 등
"""
from __future__ import annotations

import io
from PIL import Image

import httpx

from app.providers.base import BackgroundProvider
from app.providers.mock import MockBackgroundProvider
from app.settings import settings


class StabilityBackgroundProvider(BackgroundProvider):
    def __init__(self) -> None:
        self._fallback = MockBackgroundProvider()

    def generate(self, width: int, height: int, concept: dict, seed: int = 0) -> Image.Image:
        if not settings.stability_api_key:
            return self._fallback.generate(width, height, concept, seed)

        try:
            prompt_kw = concept.get("prompt_keywords", "minimal product background")
            prompt = (
                f"professional product photography background, NO product, NO text. "
                f"{prompt_kw}, studio quality, 8k"
            )
            url = "https://api.stability.ai/v2beta/stable-image/generate/core"
            headers = {
                "authorization": f"Bearer {settings.stability_api_key}",
                "accept": "image/*",
            }
            files = {"none": ""}
            data = {
                "prompt": prompt,
                "output_format": "png",
                "aspect_ratio": "1:1",
                "seed": seed,
            }
            r = httpx.post(url, headers=headers, files=files, data=data, timeout=60.0)
            if r.status_code != 200:
                print(f"[stability] {r.status_code}: {r.text[:200]}")
                return self._fallback.generate(width, height, concept, seed)
            img = Image.open(io.BytesIO(r.content)).convert("RGB")
            return img.resize((width, height), Image.LANCZOS)
        except Exception as e:
            print(f"[stability] 실패, mock 폴백: {e}")
            return self._fallback.generate(width, height, concept, seed)
