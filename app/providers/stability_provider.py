"""
Stability AI Provider — SDXL 1024 라이프스타일 배경 생성

─ 모델: stable-diffusion-xl-1024-v1-0 (cfg_scale 7, steps 30)
─ 응답 base64 → PIL Image
─ 실패 시 OpenAI(DALL-E 3) 폴백 → 그것도 실패하면 mock 폴백(서비스 안 죽음)
─ 호출당 예상 비용 logging.info 기록
"""
from __future__ import annotations

import base64
import io
import logging
from typing import Optional

import httpx
from PIL import Image

from app.providers.base import BackgroundProvider
from app.providers.mock import MockBackgroundProvider
from app.settings import settings

logger = logging.getLogger("thumbforge")

_SDXL_URL = "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image"
_EST_COST_USD = 0.018  # SDXL 1024 1장 대략 (~25원)

_DEFAULT_NEG = (
    "product, item, foreground subject, watermark, text, logo, "
    "multiple objects, blurry, low quality, distorted, person, mannequin"
)


def _prompt_pair(concept: dict, prompt: Optional[tuple]) -> tuple[str, str]:
    if prompt and prompt[0]:
        return prompt[0], (prompt[1] or _DEFAULT_NEG)
    kw = concept.get("prompt_keywords", "minimal product background")
    pos = (f"professional product photography background only, no product, no text. "
           f"{kw}, studio quality, soft lighting, 4k")
    return pos, _DEFAULT_NEG


class StabilityBackgroundProvider(BackgroundProvider):
    def __init__(self) -> None:
        self._fallback = MockBackgroundProvider()
        self.last_provider = "mock"  # 마지막 generate 가 실제로 쓴 provider

    def generate(self, width: int, height: int, concept: dict, seed: int = 0,
                 prompt: Optional[tuple] = None) -> Image.Image:
        positive, negative = _prompt_pair(concept, prompt)
        self.last_provider = "mock"

        if settings.stability_api_key:
            try:
                headers = {
                    "Authorization": f"Bearer {settings.stability_api_key}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                }
                body = {
                    "text_prompts": [
                        {"text": positive, "weight": 1.0},
                        {"text": negative, "weight": -1.0},
                    ],
                    "cfg_scale": 7,
                    "steps": 30,
                    "width": 1024,
                    "height": 1024,
                    "samples": 1,
                    "seed": int(seed) % 4294967295,
                }
                r = httpx.post(_SDXL_URL, headers=headers, json=body, timeout=90.0)
                if r.status_code == 200:
                    b64 = r.json()["artifacts"][0]["base64"]
                    img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
                    logger.info("[stability] SDXL 생성 성공 비용=~$%.4f (seed=%s)", _EST_COST_USD, seed)
                    self.last_provider = "stability"
                    return img.resize((width, height), Image.LANCZOS)
                logger.warning("[stability] %s: %s → DALL-E 폴백", r.status_code, r.text[:200])
            except Exception as e:
                logger.warning("[stability] 실패 → DALL-E 폴백: %s", e)
        else:
            logger.info("[stability] 키 없음 → DALL-E 폴백 시도")

        # 1차 폴백: OpenAI DALL-E 3
        try:
            from app.providers.openai_provider import OpenAIBackgroundProvider
            oai = OpenAIBackgroundProvider()
            if oai._client is not None:
                img = oai.generate(width, height, concept, seed=seed, prompt=(positive, negative))
                self.last_provider = oai.last_provider  # dalle 또는 mock
                return img
        except Exception as e:
            logger.warning("[stability] DALL-E 폴백도 실패: %s", e)

        # 최종 폴백: mock
        self.last_provider = "mock"
        return self._fallback.generate(width, height, concept, seed)
