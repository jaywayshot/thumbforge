"""
Provider 추상 인터페이스 - AI 교체 가능 구조
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional
from PIL import Image


class BackgroundProvider(ABC):
    """배경 생성기"""
    @abstractmethod
    def generate(
        self,
        width: int,
        height: int,
        concept: dict,
        seed: int = 0,
        prompt: Optional[tuple] = None,
    ) -> Image.Image:
        """concept 설정에 맞는 배경 이미지 (RGB or RGBA) 반환.

        prompt: (positive, negative) 영문 프롬프트. 주어지면 라이프스타일 신 생성에 사용.
                없으면 concept.prompt_keywords 로 기본 배경 생성.
        """
        ...


class TextSuggestionProvider(ABC):
    """문구 추천기"""
    @abstractmethod
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
        """{headline, sub_text, badge} 반환.

        platform: 금지어/캐시 키에 사용(없으면 전 플랫폼 안전 모드).
        fresh: 캐시를 읽지 않고 새로 생성(결과는 캐시에 저장).
        use_cache: True 일 때만 캐시 읽기/쓰기(기본 False — 직접 호출은 결정적).
                   API 라우트(/api/text/suggest)가 True 로 켠다. 평가 도구는 False.
        """
        ...


class QCProvider(ABC):
    """검수기"""
    @abstractmethod
    def review(self, image: Image.Image, meta: dict) -> dict:
        """{passed, notes, scores...} 반환"""
        ...
