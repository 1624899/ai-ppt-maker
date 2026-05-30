from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

from ppt_system.white_axis_cutout import build_white_axis_cutout


@dataclass(frozen=True)
class BackgroundModel:
    color: np.ndarray
    tolerance: int
    color_cast_tolerance: int


def refine_background_removed_image(
    source_image: Image.Image,
    removed_image: Image.Image,
    *,
    fallback_bg_threshold: int = 245,
) -> Image.Image:
    """统一精修去背结果；当前实现从源图 RGB 重新扣图，避免沿用已污染 alpha。"""
    source_rgba = np.array(source_image.convert("RGBA"), dtype=np.uint8)
    removed_rgba = np.array(removed_image.convert("RGBA"), dtype=np.uint8)
    background = estimate_background_model(
        source_rgba,
        fallback_bg_threshold=fallback_bg_threshold,
    )
    refined = refine_alpha_matte(
        source_rgba,
        removed_rgba,
        background=background,
    )
    return Image.fromarray(refined, mode="RGBA")


def estimate_background_model(
    rgba: np.ndarray,
    *,
    fallback_bg_threshold: int = 245,
) -> BackgroundModel:
    source = np.asarray(rgba, dtype=np.uint8)
    height, width = source.shape[:2]
    rgb = source[:, :, :3].astype(np.int16)
    bright_background = _bright_background_mask(rgb, fallback_bg_threshold)
    if min(height, width) <= 3 and np.any(bright_background):
        return BackgroundModel(
            color=np.array([255, 255, 255], dtype=np.int16),
            tolerance=8,
            color_cast_tolerance=8,
        )

    border_width = max(1, min(height, width) // 40)
    border_mask = np.zeros((height, width), dtype=bool)
    border_mask[:border_width, :] = True
    border_mask[-border_width:, :] = True
    border_mask[:, :border_width] = True
    border_mask[:, -border_width:] = True

    border_pixels = rgb[border_mask]
    if border_pixels.size == 0:
        return BackgroundModel(
            color=np.array([255, 255, 255], dtype=np.int16),
            tolerance=24,
            color_cast_tolerance=8,
        )

    background_color = np.median(border_pixels, axis=0)
    border_distance = np.max(np.abs(border_pixels - background_color), axis=1)
    border_cast_distance = _pixel_color_cast_distance(
        border_pixels,
        background_color=background_color,
    )
    tolerance = int(np.percentile(border_distance, 90)) + 12
    tolerance = max(12, min(tolerance, 72))
    color_cast_tolerance = int(np.percentile(border_cast_distance, 90)) + 3
    color_cast_tolerance = max(8, min(color_cast_tolerance, 24))
    if np.mean(background_color) < fallback_bg_threshold - 10 and np.any(bright_background):
        return BackgroundModel(
            color=np.array([255, 255, 255], dtype=np.int16),
            tolerance=max(8, tolerance // 2),
            color_cast_tolerance=max(8, color_cast_tolerance // 2),
        )
    return BackgroundModel(
        color=background_color,
        tolerance=tolerance,
        color_cast_tolerance=color_cast_tolerance,
    )


def build_color_guided_alpha(
    source_rgba: np.ndarray,
    *,
    background: BackgroundModel,
) -> np.ndarray:
    """兼容旧调用名：返回新白轴抠图得到的 alpha 证据。"""
    artifacts = build_white_axis_cutout(
        np.asarray(source_rgba, dtype=np.uint8),
        background_color=background.color,
        background_tolerance=background.tolerance,
        background_cast_tolerance=background.color_cast_tolerance,
    )
    return artifacts.final_alpha


def refine_alpha_matte(
    source_rgba: np.ndarray,
    removed_rgba: np.ndarray,
    *,
    background: BackgroundModel,
) -> np.ndarray:
    """从头生成 alpha：肉眼白全透明，非白前景不做任何外扩式增强。"""
    source = np.asarray(source_rgba, dtype=np.uint8)
    artifacts = build_white_axis_cutout(
        source,
        background_color=background.color,
        background_tolerance=background.tolerance,
        background_cast_tolerance=background.color_cast_tolerance,
    )
    return artifacts.rgba


def _bright_background_mask(rgb: np.ndarray, fallback_bg_threshold: int) -> np.ndarray:
    return (
        (rgb[:, :, 0] >= fallback_bg_threshold)
        & (rgb[:, :, 1] >= fallback_bg_threshold)
        & (rgb[:, :, 2] >= fallback_bg_threshold)
    )


def _color_distance(rgb: np.ndarray, background_color: np.ndarray) -> np.ndarray:
    return np.max(np.abs(rgb - background_color.reshape(1, 1, 3)), axis=2)


def _color_cast_distance(rgb: np.ndarray, background_color: np.ndarray) -> np.ndarray:
    background_cast = background_color.reshape(1, 1, 3) - np.round(np.mean(background_color)).astype(np.int16)
    pixel_mean = np.round(np.mean(rgb, axis=2, keepdims=True)).astype(np.int16)
    pixel_cast = rgb - pixel_mean
    return np.max(np.abs(pixel_cast - background_cast), axis=2)


def _pixel_color_cast_distance(border_pixels: np.ndarray, *, background_color: np.ndarray) -> np.ndarray:
    if border_pixels.size == 0:
        return np.zeros((0,), dtype=np.int16)
    background_cast = background_color.reshape(1, 3) - np.round(np.mean(background_color)).astype(np.int16)
    pixel_mean = np.round(np.mean(border_pixels, axis=1, keepdims=True)).astype(np.int16)
    pixel_cast = border_pixels - pixel_mean
    return np.max(np.abs(pixel_cast - background_cast), axis=1)
