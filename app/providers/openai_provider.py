"""
OpenAI Provider - 키 없으면 import 시점에 raise 하지 않고
                  실제 호출 시점에 mock으로 폴백
"""
from __future__ import annotations

import base64
import io
import json
import os
from typing import Optional

from PIL import Image

from app.providers.base import BackgroundProvider, TextSuggestionProvider
from app.providers.mock import MockBackgroundProvider, MockTextSuggestionProvider
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


# 기본 문구 추천 모델 (환경변수 OPENAI_TEXT_MODEL 로 덮어쓰기 가능)
_DEFAULT_TEXT_MODEL = os.getenv("OPENAI_TEXT_MODEL", "gpt-4o-mini")


class OpenAITextSuggestionProvider(TextSuggestionProvider):
    """
    실제 LLM(OpenAI Chat) 기반 매출형 문구 추천.

    설계 원칙
    ─ OPENAI_API_KEY 가 있을 때만 실제 호출, 없으면 mock 폴백
    ─ response_format={"type":"json_object"} 로 JSON 강제
    ─ 카테고리/컨셉/플랫폼 금지어를 system 프롬프트에 주입해 위험 표현 차단
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

    # ───────── 금지어 수집 ─────────

    def _gather_forbidden(self, category: str, concept: str) -> list[str]:
        """카테고리/컨셉/플랫폼에서 금지어를 모아 중복 제거.

        suggest() 시그니처에 platform 인자가 없으므로, 어떤 플랫폼에
        업로드해도 안전하도록 모든 플랫폼 금지어의 합집합을 사용한다.
        """
        # 지연 임포트: 테스트/임포트 시점 사이클 방지
        from app.services.concept_loader import (
            get_categories,
            get_concept,
            get_platforms,
        )

        words: list[str] = []

        try:
            concept_cfg = get_concept(concept) or {}
            words += list(concept_cfg.get("forbidden_words", []) or [])
        except Exception:
            pass

        try:
            cat_cfg = get_categories().get(category, {}) or {}
            words += list(cat_cfg.get("forbidden_words", []) or [])
        except Exception:
            pass

        try:
            for p in get_platforms().values():
                words += list(p.get("forbidden_words", []) or [])
        except Exception:
            pass

        # 순서 보존 중복 제거
        seen: set[str] = set()
        uniq: list[str] = []
        for w in words:
            if w and w not in seen:
                seen.add(w)
                uniq.append(w)
        return uniq

    def _build_messages(
        self, category: str, concept: str, product_hint: Optional[str]
    ) -> list[dict]:
        forbidden = self._gather_forbidden(category, concept)
        forbidden_str = ", ".join(forbidden) if forbidden else "(없음)"

        system = (
            "너는 한국 이커머스 썸네일 카피라이터다. "
            "제품 썸네일에 들어갈 매출 전환형 문구를 만든다.\n"
            "반드시 다음 키만 가진 JSON 객체로만 답한다: "
            '{"headline": "...", "sub_text": "...", "badge": "..."}\n'
            "- headline: 14자 이내의 강렬한 한글 헤드라인\n"
            "- sub_text: 8자 내외의 보조 문구(배송/품질 등 사실 기반)\n"
            "- badge: BEST/NEW/HOT 같은 짧은 뱃지(영문 또는 한글, 6자 이내)\n"
            "절대 사용 금지 단어/표현(법적·정책적 위험): "
            f"{forbidden_str}. 이 단어들은 변형 포함 어떤 형태로도 쓰지 마라.\n"
            "객관적으로 입증 불가능한 과장(최고/유일/100% 등)은 금지한다."
        )
        user_parts = [
            f"카테고리: {category}",
            f"컨셉: {concept}",
        ]
        if product_hint:
            user_parts.append(f"제품 힌트: {product_hint}")
        user = "\n".join(user_parts) + "\n위 정보에 맞는 문구 JSON을 생성해라."

        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def _normalize(self, data: dict) -> dict:
        """파싱 결과를 {headline, sub_text, badge} 로 정규화. 비면 mock 값으로 보충."""
        mock = self._fallback.suggest("general", "general")
        headline = str(data.get("headline") or "").strip() or mock["headline"]
        sub_text = str(data.get("sub_text") or "").strip() or mock["sub_text"]
        badge = str(data.get("badge") or "").strip() or mock["badge"]
        return {"headline": headline, "sub_text": sub_text, "badge": badge}

    def suggest(
        self, category: str, concept: str, product_hint: Optional[str] = None
    ) -> dict:
        if self._client is None:
            # 키 없음/패키지 없음 → mock 폴백
            return self._fallback.suggest(category, concept, product_hint)

        try:
            messages = self._build_messages(category, concept, product_hint)
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.8,
            )
            content = resp.choices[0].message.content
            data = json.loads(content)
            if not isinstance(data, dict):
                raise ValueError("JSON 객체가 아님")
            return self._normalize(data)
        except Exception as e:
            print(f"[openai] 문구 추천 실패, mock 폴백: {e}")
            return self._fallback.suggest(category, concept, product_hint)
