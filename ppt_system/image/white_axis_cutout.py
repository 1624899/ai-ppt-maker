from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ppt_system.image.cv_mask_components import find_mask_components, grow_mask_from_seed
from ppt_system.image.visual_white_axis import build_visual_white_mask, remove_visual_white_from_alpha


@dataclass(frozen=True)
class WhiteAxisCutoutOptions:
    seed_color_margin: int = 6
    seed_cast_margin: int = 2
    seed_dark_gap: float = 32.0
    seed_saturation_floor: int = 16
    candidate_color_margin: int = -6
    candidate_cast_margin: int = -4
    candidate_dark_gap: float = 10.0
    candidate_saturation_floor: int = 8
    alpha_fade_start: float = 4.0
    alpha_soft_band: float = 46.0
    min_connected_alpha: int = 20
    seed_alpha_floor: int = 232
    small_component_area: int = 3
    small_component_alpha: int = 96


@dataclass(frozen=True)
class WhiteAxisCutoutArtifacts:
    rgba: np.ndarray
    visual_white_mask: np.ndarray
    seed_mask: np.ndarray
    candidate_mask: np.ndarray
    connected_mask: np.ndarray
    raw_alpha: np.ndarray
    final_alpha: np.ndarray


DEFAULT_WHITE_AXIS_CUTOUT_OPTIONS = WhiteAxisCutoutOptions()


def build_white_axis_cutout(
    source_rgba: np.ndarray,
    *,
    background_color: np.ndarray,
    background_tolerance: int,
    background_cast_tolerance: int,
    options: WhiteAxisCutoutOptions = DEFAULT_WHITE_AXIS_CUTOUT_OPTIONS,
) -> WhiteAxisCutoutArtifacts:
    """从 RGB 重新推导透明度：肉眼白硬删除，非白前景只在原始证据内保留。"""
    source = np.asarray(source_rgba, dtype=np.uint8)
    if source.ndim != 3 or source.shape[2] != 4:
        empty = np.zeros(source.shape[:2] if source.ndim >= 2 else (0, 0), dtype=np.uint8)
        rgba = np.zeros((*empty.shape, 4), dtype=np.uint8)
        return WhiteAxisCutoutArtifacts(
            rgba=rgba,
            visual_white_mask=empty.astype(bool),
            seed_mask=empty.astype(bool),
            candidate_mask=empty.astype(bool),
            connected_mask=empty.astype(bool),
            raw_alpha=empty,
            final_alpha=empty,
        )

    rgb = source[:, :, :3]
    rgb_int16 = rgb.astype(np.int16)
    background = np.asarray(background_color, dtype=np.int16).reshape(3)
    background_mean = float(np.mean(background.astype(np.float32)))

    visual_white_mask = build_visual_white_mask(
        rgb,
        background_color=background,
        background_tolerance=background_tolerance,
    )
    color_distance = _color_distance(rgb_int16, background)
    color_cast_distance = _color_cast_distance(rgb_int16, background)
    brightness = np.mean(rgb_int16.astype(np.float32), axis=2)
    saturation = np.max(rgb_int16, axis=2) - np.min(rgb_int16, axis=2)

    non_white = ~visual_white_mask
    seed_mask = non_white & _build_seed_mask(
        color_distance=color_distance,
        color_cast_distance=color_cast_distance,
        brightness=brightness,
        saturation=saturation,
        background_mean=background_mean,
        background_tolerance=background_tolerance,
        background_cast_tolerance=background_cast_tolerance,
        options=options,
    )
    candidate_mask = non_white & _build_candidate_mask(
        color_distance=color_distance,
        color_cast_distance=color_cast_distance,
        brightness=brightness,
        saturation=saturation,
        background_mean=background_mean,
        background_tolerance=background_tolerance,
        background_cast_tolerance=background_cast_tolerance,
        options=options,
    )
    connected_mask = grow_mask_from_seed(
        candidate_mask=candidate_mask,
        seed_mask=seed_mask,
        connectivity=8,
    )

    raw_alpha = _build_alpha_from_rgb_evidence(
        color_distance=color_distance,
        color_cast_distance=color_cast_distance,
        brightness=brightness,
        saturation=saturation,
        background_mean=background_mean,
        connected_mask=connected_mask,
        seed_mask=seed_mask,
        options=options,
    )
    final_alpha = _remove_weak_noise_components(
        raw_alpha,
        seed_mask=seed_mask,
        options=options,
    )
    final_alpha = remove_visual_white_from_alpha(
        final_alpha,
        visual_white_mask=visual_white_mask,
    )
    final_alpha = np.minimum(final_alpha, source[:, :, 3])

    result = np.zeros_like(source)
    visible = final_alpha > 0
    result[visible, :3] = rgb[visible]
    result[:, :, 3] = final_alpha
    return WhiteAxisCutoutArtifacts(
        rgba=result,
        visual_white_mask=visual_white_mask,
        seed_mask=seed_mask,
        candidate_mask=candidate_mask,
        connected_mask=connected_mask,
        raw_alpha=raw_alpha,
        final_alpha=final_alpha,
    )


def _build_seed_mask(
    *,
    color_distance: np.ndarray,
    color_cast_distance: np.ndarray,
    brightness: np.ndarray,
    saturation: np.ndarray,
    background_mean: float,
    background_tolerance: int,
    background_cast_tolerance: int,
    options: WhiteAxisCutoutOptions,
) -> np.ndarray:
    color_seed = color_distance >= int(background_tolerance) + int(options.seed_color_margin)
    cast_seed = color_cast_distance >= int(background_cast_tolerance) + int(options.seed_cast_margin)
    dark_seed = brightness <= background_mean - float(options.seed_dark_gap)
    saturated_seed = saturation >= int(options.seed_saturation_floor)
    return (color_seed | cast_seed | dark_seed) & (saturated_seed | dark_seed | cast_seed)


def _build_candidate_mask(
    *,
    color_distance: np.ndarray,
    color_cast_distance: np.ndarray,
    brightness: np.ndarray,
    saturation: np.ndarray,
    background_mean: float,
    background_tolerance: int,
    background_cast_tolerance: int,
    options: WhiteAxisCutoutOptions,
) -> np.ndarray:
    color_floor = max(3, int(background_tolerance) + int(options.candidate_color_margin))
    cast_floor = max(2, int(background_cast_tolerance) + int(options.candidate_cast_margin))
    color_candidate = color_distance >= color_floor
    cast_candidate = color_cast_distance >= cast_floor
    dark_candidate = brightness <= background_mean - float(options.candidate_dark_gap)
    saturated_candidate = saturation >= int(options.candidate_saturation_floor)
    return (color_candidate | cast_candidate | dark_candidate) & (saturated_candidate | dark_candidate | cast_candidate)


def _build_alpha_from_rgb_evidence(
    *,
    color_distance: np.ndarray,
    color_cast_distance: np.ndarray,
    brightness: np.ndarray,
    saturation: np.ndarray,
    background_mean: float,
    connected_mask: np.ndarray,
    seed_mask: np.ndarray,
    options: WhiteAxisCutoutOptions,
) -> np.ndarray:
    dark_distance = np.maximum(0.0, background_mean - brightness)
    effective_distance = np.maximum.reduce(
        [
            color_distance.astype(np.float32),
            color_cast_distance.astype(np.float32) * 2.4,
            dark_distance.astype(np.float32) * 1.15,
            saturation.astype(np.float32) * 1.35,
        ]
    )
    alpha_scale = np.clip(
        (effective_distance - float(options.alpha_fade_start)) / max(1.0, float(options.alpha_soft_band)),
        0.0,
        1.0,
    )
    alpha = np.round(alpha_scale * 255.0).astype(np.uint8)
    alpha[connected_mask] = np.maximum(alpha[connected_mask], np.uint8(options.min_connected_alpha))
    alpha[seed_mask] = np.maximum(alpha[seed_mask], np.uint8(options.seed_alpha_floor))
    alpha[~connected_mask] = 0
    return alpha


def _remove_weak_noise_components(
    alpha: np.ndarray,
    *,
    seed_mask: np.ndarray,
    options: WhiteAxisCutoutOptions,
) -> np.ndarray:
    result = np.asarray(alpha, dtype=np.uint8).copy()
    visible = result > 0
    if not np.any(visible):
        return result

    seeds = np.asarray(seed_mask, dtype=bool)
    for component in find_mask_components(visible, connectivity=8):
        left = int(component["left"])
        top = int(component["top"])
        right = int(component["right"])
        bottom = int(component["bottom"])
        local_mask = np.asarray(component["mask"], dtype=bool)
        alpha_crop = result[top:bottom, left:right]
        seed_crop = seeds[top:bottom, left:right]
        if np.any(seed_crop & local_mask):
            continue

        area = int(component["area"])
        max_alpha = int(np.max(alpha_crop[local_mask])) if np.any(local_mask) else 0
        if area <= int(options.small_component_area) or max_alpha <= int(options.small_component_alpha):
            alpha_crop[local_mask] = 0
            result[top:bottom, left:right] = alpha_crop
    return result


def _color_distance(rgb: np.ndarray, background_color: np.ndarray) -> np.ndarray:
    return np.max(np.abs(rgb - background_color.reshape(1, 1, 3)), axis=2)


def _color_cast_distance(rgb: np.ndarray, background_color: np.ndarray) -> np.ndarray:
    background_cast = background_color.reshape(1, 1, 3) - np.round(np.mean(background_color)).astype(np.int16)
    pixel_mean = np.round(np.mean(rgb, axis=2, keepdims=True)).astype(np.int16)
    pixel_cast = rgb - pixel_mean
    return np.max(np.abs(pixel_cast - background_cast), axis=2)
