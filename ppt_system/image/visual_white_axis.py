from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class VisualWhiteOptions:
    min_brightness: float = 242.0
    min_channel_floor: int = 236
    background_brightness_gap: float = 18.0
    background_channel_gap: int = 24
    max_chroma: int = 12
    max_cast_distance: int = 6
    max_background_distance: int = 22
    background_tolerance_extra: int = 10
    absolute_min_brightness: float = 250.0
    absolute_min_channel_floor: int = 246
    absolute_max_chroma: int = 12
    absolute_max_cast_distance: int = 8


DEFAULT_VISUAL_WHITE_OPTIONS = VisualWhiteOptions()


def build_visual_white_mask(
    rgb: np.ndarray,
    *,
    background_color: np.ndarray,
    background_tolerance: int = 0,
    options: VisualWhiteOptions = DEFAULT_VISUAL_WHITE_OPTIONS,
) -> np.ndarray:
    """识别肉眼白像素：高亮、低色度、接近中性白轴，不依赖是否连到外边界。"""
    source = np.asarray(rgb)
    if source.ndim != 3 or source.shape[2] != 3:
        if source.ndim >= 2:
            return np.zeros(source.shape[:2], dtype=bool)
        return np.zeros((0, 0), dtype=bool)

    rgb_int16 = source.astype(np.int16)
    background = _resolve_background_color(background_color)

    brightness = np.mean(rgb_int16.astype(np.float32), axis=2)
    channel_floor = np.min(rgb_int16, axis=2)
    chroma = np.max(rgb_int16, axis=2) - channel_floor
    color_distance = np.max(np.abs(rgb_int16 - background.reshape(1, 1, 3)), axis=2)
    cast_distance = _color_cast_distance(rgb_int16, background)

    background_mean = float(np.mean(background.astype(np.float32)))
    background_floor = int(np.min(background))
    brightness_floor = max(
        float(options.min_brightness),
        background_mean - float(options.background_brightness_gap),
    )
    channel_floor_threshold = max(
        int(options.min_channel_floor),
        background_floor - int(options.background_channel_gap),
    )
    background_distance_ceiling = max(
        int(options.max_background_distance),
        int(background_tolerance) + int(options.background_tolerance_extra),
    )

    close_neutral_white = (
        (brightness >= brightness_floor)
        & (channel_floor >= channel_floor_threshold)
        & (chroma <= int(options.max_chroma))
        & (cast_distance <= int(options.max_cast_distance))
        & (color_distance <= background_distance_ceiling)
    )
    absolute_neutral_white = (
        (brightness >= float(options.absolute_min_brightness))
        & (channel_floor >= int(options.absolute_min_channel_floor))
        & (chroma <= int(options.absolute_max_chroma))
        & (cast_distance <= int(options.absolute_max_cast_distance))
    )
    return close_neutral_white | absolute_neutral_white


def remove_visual_white_from_alpha(
    alpha: np.ndarray,
    *,
    visual_white_mask: np.ndarray,
) -> np.ndarray:
    """把肉眼白对应的 alpha 归零，作为后续增强步骤不可绕过的硬约束。"""
    source = np.asarray(alpha, dtype=np.uint8)
    if source.ndim != 2:
        return np.array(source, copy=True)

    white = np.asarray(visual_white_mask, dtype=bool)
    if white.shape != source.shape:
        return np.array(source, copy=True)

    result = np.array(source, copy=True)
    result[white] = 0
    return result


def _resolve_background_color(background_color: np.ndarray) -> np.ndarray:
    resolved = np.asarray(background_color, dtype=np.int16).reshape(-1)
    if resolved.size != 3:
        return np.array([255, 255, 255], dtype=np.int16)
    return resolved.astype(np.int16)


def _color_cast_distance(rgb: np.ndarray, background_color: np.ndarray) -> np.ndarray:
    background_cast = background_color.reshape(1, 1, 3) - np.round(np.mean(background_color)).astype(np.int16)
    pixel_mean = np.round(np.mean(rgb, axis=2, keepdims=True)).astype(np.int16)
    pixel_cast = rgb - pixel_mean
    return np.max(np.abs(pixel_cast - background_cast), axis=2)
