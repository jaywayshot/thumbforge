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
    ) -> Image.Image:
        """concept 설정에 맞는 배경 이미지 (RGB or RGBA) 반환"""
        ...


class TextSuggestionProvider(ABC):
    """문구 추천기"""
    @abstractmethod
    def suggest(
        self,
        category: str,
        concept: str,
        product_hint: Optional[str] = None,
    ) -> dict:
        """{headline, sub_text, badge} 반환"""
        ...


class QCProvider(ABC):
    """검수기"""
    @abstractmethod
    def review(self, image: Image.Image, meta: dict) -> dict:
        """{passed, notes, scores...} 반환"""
        ...
