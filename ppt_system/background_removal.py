from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Callable

import numpy as np
from PIL import Image

from ppt_system.model_cache_runtime import configure_model_cache_environment


@dataclass(frozen=True)
class BackgroundRemovalResult:
    image: Image.Image
    strategy: str
    warning: str | None = None


def remove_background(
    image: Image.Image,
    *,
    fallback_bg_threshold: int = 245,
) -> BackgroundRemovalResult:
    configure_model_cache_environment()
    alpha = image.getchannel("A")
    if alpha.getextrema()[0] < 255:
        return BackgroundRemovalResult(image=image.copy(), strategy="preserve-alpha")

    rembg_remove = _load_rembg_remove()
    if rembg_remove is None:
        return _remove_background_with_threshold(
            image,
            fallback_bg_threshold,
            warning="未安装 rembg，已回退到阈值去背",
        )

    try:
        removed = rembg_remove(image)
        normalized = _normalize_removed_image(removed)
    except Exception as exc:
        # rembg 依赖外部模型文件，首次下载失败、缓存损坏或推理异常时都统一回退。
        return _remove_background_with_threshold(
            image,
            fallback_bg_threshold,
            warning=f"rembg 运行失败（{_summarize_exception(exc)}），已回退到阈值去背",
        )

    return BackgroundRemovalResult(image=normalized, strategy="rembg")


def _load_rembg_remove() -> Callable[[Image.Image], Image.Image | bytes] | None:
    try:
        from rembg import remove
    except ImportError:
        return None
    return remove


def _remove_background_with_threshold(
    image: Image.Image,
    fallback_bg_threshold: int,
    *,
    warning: str,
) -> BackgroundRemovalResult:
    rgba = np.array(image.convert("RGBA"), dtype=np.uint8)
    background_mask = _detect_background_mask(rgba, fallback_bg_threshold)
    rgba[background_mask, 3] = 0
    processed = Image.fromarray(rgba, mode="RGBA")
    return BackgroundRemovalResult(image=processed, strategy="threshold", warning=warning)


def _normalize_removed_image(removed: Image.Image | bytes) -> Image.Image:
    if isinstance(removed, Image.Image):
        return removed.convert("RGBA")
    if isinstance(removed, bytes):
        return Image.open(BytesIO(removed)).convert("RGBA")
    raise TypeError(f"不支持的 rembg 输出类型：{type(removed)!r}")


def _summarize_exception(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return message
    return exc.__class__.__name__


def _detect_background_mask(rgba: np.ndarray, fallback_bg_threshold: int) -> np.ndarray:
    height, width = rgba.shape[:2]
    rgb = rgba[:, :, :3].astype(np.int16)

    border_width = max(1, min(height, width) // 40)
    border_mask = np.zeros((height, width), dtype=bool)
    border_mask[:border_width, :] = True
    border_mask[-border_width:, :] = True
    border_mask[:, :border_width] = True
    border_mask[:, -border_width:] = True

    border_pixels = rgb[border_mask]
    if border_pixels.size == 0:
        return _bright_background_mask(rgb, fallback_bg_threshold)

    background_color = np.median(border_pixels, axis=0)
    border_distance = np.max(np.abs(border_pixels - background_color), axis=1)
    tolerance = int(np.percentile(border_distance, 90)) + 12
    tolerance = max(12, min(tolerance, 72))

    near_border_color = np.max(np.abs(rgb - background_color), axis=2) <= tolerance
    bright_background = _bright_background_mask(rgb, fallback_bg_threshold)
    border_match_ratio = float(np.mean(near_border_color[border_mask]))
    if border_match_ratio < 0.35 and np.any(bright_background[border_mask]):
        return _flood_fill_from_border(bright_background)
    if np.mean(background_color) >= fallback_bg_threshold - 10:
        candidate_mask = near_border_color | bright_background
    else:
        candidate_mask = near_border_color

    return _flood_fill_from_border(candidate_mask)


def _bright_background_mask(rgb: np.ndarray, fallback_bg_threshold: int) -> np.ndarray:
    return (
        (rgb[:, :, 0] >= fallback_bg_threshold)
        & (rgb[:, :, 1] >= fallback_bg_threshold)
        & (rgb[:, :, 2] >= fallback_bg_threshold)
    )


def _flood_fill_from_border(candidate_mask: np.ndarray) -> np.ndarray:
    height, width = candidate_mask.shape
    visited = np.zeros((height, width), dtype=bool)
    queue: list[tuple[int, int]] = []

    def push(y: int, x: int) -> None:
        if visited[y, x] or not candidate_mask[y, x]:
            return
        visited[y, x] = True
        queue.append((y, x))

    for x in range(width):
        push(0, x)
        push(height - 1, x)
    for y in range(height):
        push(y, 0)
        push(y, width - 1)

    cursor = 0
    while cursor < len(queue):
        y, x = queue[cursor]
        cursor += 1
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny = y + dy
            nx = x + dx
            if 0 <= ny < height and 0 <= nx < width:
                push(ny, nx)
    return visited
