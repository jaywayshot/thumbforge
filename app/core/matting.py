"""
누끼(배경 제거) 처리
── 1차: rembg (AI 모델)
── 폴백: 흰배경 자동 감지 후 알파 컷
── 이미 알파가 있으면 그대로 통과
"""
from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from app.settings import settings


@lru_cache(maxsize=1)
def _get_rembg_session():
    """rembg 세션은 한 번만 만들고 재사용 (모델 로딩 시간 절감)"""
    try:
        from rembg import new_session
        return new_session(settings.matting_model)
    except Exception as e:
        print(f"[matting] rembg 사용 불가, 폴백 모드로 진행: {e}")
        return None


def _remove_with_rembg(img: Image.Image) -> Optional[Image.Image]:
    session = _get_rembg_session()
    if session is None:
        return None
    try:
        from rembg import remove
        out = remove(img, session=session)
        if out.mode != "RGBA":
            out = out.convert("RGBA")
        return out
    except Exception as e:
        print(f"[matting] rembg 실패: {e}")
        return None


def _remove_white_bg_fallback(img: Image.Image, threshold: int = 240) -> Image.Image:
    """rembg 없이 동작 가능한 흰배경 자동 제거"""
    rgba = img.convert("RGBA")
    arr = np.array(rgba)
    r, g, b, a = arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3]
    white_mask = (r >= threshold) & (g >= threshold) & (b >= threshold)
    # 가장자리에서 시작하는 흰 영역만 제거 (제품 내부 흰 부분 보존)
    from collections import deque
    h, w = white_mask.shape
    visited = np.zeros_like(white_mask, dtype=bool)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if white_mask[y, x] and not visited[y, x]:
                q.append((y, x)); visited[y, x] = True
    for y in range(h):
        for x in (0, w - 1):
            if white_mask[y, x] and not visited[y, x]:
                q.append((y, x)); visited[y, x] = True
    while q:
        y, x = q.popleft()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and white_mask[ny, nx] and not visited[ny, nx]:
                visited[ny, nx] = True
                q.append((ny, nx))
    arr[..., 3] = np.where(visited, 0, a)
    return Image.fromarray(arr, mode="RGBA")


def has_meaningful_alpha(img: Image.Image, ratio_threshold: float = 0.01) -> bool:
    """이미 누끼된 이미지인지 판단"""
    if img.mode != "RGBA":
        return False
    a = np.array(img.split()[-1])
    transparent_ratio = float(np.mean(a < 10))
    return transparent_ratio > ratio_threshold


def remove_background(img: Image.Image) -> Image.Image:
    """
    공개 API. 결과는 항상 RGBA.
    이미 알파가 있으면 그대로 반환.
    """
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    if has_meaningful_alpha(img):
        return img

    out = _remove_with_rembg(img)
    if out is not None:
        return out

    # 폴백
    return _remove_white_bg_fallback(img)


def crop_to_content(img: Image.Image, padding: int = 0) -> Image.Image:
    """알파 영역에 맞춰 크롭 (제품 주변 빈 공간 제거)"""
    if img.mode != "RGBA":
        return img
    alpha = np.array(img.split()[-1])
    ys, xs = np.where(alpha > 5)
    if len(xs) == 0 or len(ys) == 0:
        return img
    x0, x1 = max(0, xs.min() - padding), min(img.width, xs.max() + 1 + padding)
    y0, y1 = max(0, ys.min() - padding), min(img.height, ys.max() + 1 + padding)
    return img.crop((x0, y0, x1, y1))
