"""
Anthropic(Claude) 문구 추천 Provider

설계 원칙 (OpenAI Provider 와 대칭)
─ ANTHROPIC_API_KEY 가 있을 때만 실제 호출, 없으면 mock 폴백
─ system 프롬프트에 JSON 스키마 + 카테고리/컨셉/플랫폼 금지어 주입
─ 응답을 JSON 으로 파싱, 실패 시 예외로 죽지 않고 mock 폴백
─ anthropic 패키지는 선택적 의존성 (미설치 시 import 시점에 죽지 않음)
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional

from app.providers.base import TextSuggestionProvider
from app.providers.mock import MockTextSuggestionProvider
from app.settings import settings

# 기본 모델 (환경변수 ANTHROPIC_TEXT_MODEL 로 덮어쓰기 가능)
_DEFAULT_TEXT_MODEL = os.getenv("ANTHROPIC_TEXT_MODEL", "claude-haiku-4-5-20251001")


def _gather_forbidden(category: str, concept: str) -> list[str]:
    """카테고리/컨셉/플랫폼 금지어 합집합 (어느 플랫폼에 올려도 안전)."""
    from app.services.concept_loader import (
        get_categories,
        get_concept,
        get_platforms,
    )

    words: list[str] = []
    try:
        words += list((get_concept(concept) or {}).get("forbidden_words", []) or [])
    except Exception:
        pass
    try:
        words += list((get_categories().get(category, {}) or {}).get("forbidden_words", []) or [])
    except Exception:
        pass
    try:
        for p in get_platforms().values():
            words += list(p.get("forbidden_words", []) or [])
    except Exception:
        pass

    seen: set[str] = set()
    uniq: list[str] = []
    for w in words:
        if w and w not in seen:
            seen.add(w)
            uniq.append(w)
    return uniq


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

    def _system_prompt(self, category: str, concept: str) -> str:
        forbidden = _gather_forbidden(category, concept)
        forbidden_str = ", ".join(forbidden) if forbidden else "(없음)"
        return (
            "너는 한국 이커머스 썸네일 카피라이터다. "
            "제품 썸네일용 매출 전환형 문구를 만든다.\n"
            "반드시 아래 키만 가진 JSON 객체 하나만 출력한다(코드블록/설명 금지): "
            '{"headline": "...", "sub_text": "...", "badge": "..."}\n'
            "- headline: 14자 이내 강렬한 한글 헤드라인\n"
            "- sub_text: 8자 내외 보조 문구(배송/품질 등 사실 기반)\n"
            "- badge: 6자 이내 짧은 뱃지\n"
            f"절대 사용 금지 단어/표현(법적·정책적 위험): {forbidden_str}. "
            "변형 포함 어떤 형태로도 쓰지 마라. 입증 불가 과장(최고/유일/100% 등)도 금지."
        )

    def _normalize(self, data: dict) -> dict:
        mock = self._fallback.suggest("general", "general")
        return {
            "headline": (str(data.get("headline") or "").strip() or mock["headline"]),
            "sub_text": (str(data.get("sub_text") or "").strip() or mock["sub_text"]),
            "badge": (str(data.get("badge") or "").strip() or mock["badge"]),
        }

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
    def _loads_lenient(text: str) -> dict:
        """순수 JSON 우선, 실패 시 본문에서 첫 { ... } 블록 추출 시도."""
        try:
            return json.loads(text)
        except Exception:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if not m:
                raise
            return json.loads(m.group(0))

    def suggest(
        self, category: str, concept: str, product_hint: Optional[str] = None
    ) -> dict:
        if self._client is None:
            return self._fallback.suggest(category, concept, product_hint)
        try:
            user = f"카테고리: {category}\n컨셉: {concept}"
            if product_hint:
                user += f"\n제품 힌트: {product_hint}"
            user += "\n위 정보에 맞는 문구 JSON을 생성해라."

            resp = self._client.messages.create(
                model=self._model,
                max_tokens=300,
                system=self._system_prompt(category, concept),
                messages=[{"role": "user", "content": user}],
            )
            data = self._loads_lenient(self._extract_text(resp))
            if not isinstance(data, dict):
                raise ValueError("JSON 객체가 아님")
            return self._normalize(data)
        except Exception as e:
            print(f"[anthropic] 문구 추천 실패, mock 폴백: {e}")
            return self._fallback.suggest(category, concept, product_hint)
