from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

from ppt_system.binary_morphology import morphology_close
from ppt_system.cv_mask_components import find_mask_components, flood_mask_from_border, grow_mask_from_seed


@dataclass(frozen=True)
class BackgroundEstimate:
    color: np.ndarray
    tolerance: int
    color_cast_tolerance: int


@dataclass(frozen=True)
class ForegroundReconstructionOptions:
    strong_color_margin: int = 6
    strong_cast_margin: int = 2
    candidate_color_margin: int = -2
    candidate_cast_margin: int = -4
    strong_saturation_floor: int = 28
    candidate_saturation_floor: int = 36
    dark_brightness_gap: float = 32.0
    very_dark_brightness_gap: float = 56.0
    pale_brightness_gap: float = 22.0
    pale_max_saturation: int = 42
    pale_extra_color_tolerance: int = 16
    pale_extra_cast_tolerance: int = 4
    boundary_trim_iterations: int = 2
    boundary_trim_neighbor_limit: int = 7
    boundary_recolor_brightness_gap: float = -4.0
    boundary_recolor_saturation_ceiling: int = 132
    support_radius: int = 5
    pale_component_trim_iterations: int = 2
    pale_component_min_saturation: int = 52
    support_recolor_distance_floor: int = 4
    enclosed_fill_min_area: int = 64
    enclosed_fill_min_side: int = 6
    enclosed_fill_fill_ratio: float = 0.34
    enclosed_fill_close_kernel: int = 3
    enclosed_fill_min_color_distance: int = 10
    enclosed_fill_min_cast_distance: int = 6
    enclosed_fill_max_brightness_gap: float = 8.0


DEFAULT_FOREGROUND_RECONSTRUCTION_OPTIONS = ForegroundReconstructionOptions()


def reconstruct_foreground_rgba(
    image: Image.Image,
    *,
    fallback_bg_threshold: int = 245,
    options: ForegroundReconstructionOptions = DEFAULT_FOREGROUND_RECONSTRUCTION_OPTIONS,
) -> np.ndarray:
    """基于背景估计进行偏激进的硬扣，只保留高置信主体。"""
    source_rgba = np.array(image.convert("RGBA"), dtype=np.uint8)
    rgb = source_rgba[:, :, :3]
    background = estimate_background(rgb, fallback_bg_threshold=fallback_bg_threshold)
    core_mask = build_foreground_core_mask(
        rgb,
        background=background,
        options=options,
    )
    compacted_rgb = _compact_boundary_colors(
        rgb,
        core_mask=core_mask,
        background=background,
        options=options,
    )
    restored_fill_mask = _restore_enclosed_fill_regions(
        core_mask,
        rgb=rgb,
        background=background,
        options=options,
    )
    final_mask = core_mask | restored_fill_mask

    result_rgb = np.zeros_like(rgb)
    result_alpha = np.zeros(core_mask.shape, dtype=np.uint8)
    if not np.any(final_mask):
        return np.dstack((result_rgb, result_alpha))

    result_rgb[final_mask] = rgb[final_mask]
    result_rgb[core_mask] = compacted_rgb[core_mask]
    result_alpha[final_mask] = 255
    return np.dstack((result_rgb, result_alpha))


def estimate_background(
    rgb: np.ndarray,
    *,
    fallback_bg_threshold: int = 245,
) -> BackgroundEstimate:
    resolved_rgb = np.asarray(rgb, dtype=np.uint8)
    height, width = resolved_rgb.shape[:2]
    rgb_int16 = resolved_rgb.astype(np.int16)
    bright_background = _bright_background_mask(rgb_int16, fallback_bg_threshold)

    if min(height, width) <= 3 and np.any(bright_background):
        return BackgroundEstimate(
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

    border_pixels = rgb_int16[border_mask]
    if border_pixels.size == 0:
        return BackgroundEstimate(
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
        return BackgroundEstimate(
            color=np.array([255, 255, 255], dtype=np.int16),
            tolerance=max(8, tolerance // 2),
            color_cast_tolerance=max(8, color_cast_tolerance // 2),
        )
    return BackgroundEstimate(
        color=background_color,
        tolerance=tolerance,
        color_cast_tolerance=color_cast_tolerance,
    )


def build_foreground_core_mask(
    rgb: np.ndarray,
    *,
    background: BackgroundEstimate,
    options: ForegroundReconstructionOptions = DEFAULT_FOREGROUND_RECONSTRUCTION_OPTIONS,
) -> np.ndarray:
    rgb_uint8 = np.asarray(rgb, dtype=np.uint8)
    rgb_int16 = rgb_uint8.astype(np.int16)
    color_distance = _color_distance(rgb_int16, background.color)
    color_cast_distance = _color_cast_distance(rgb_int16, background.color)
    brightness = np.mean(rgb_uint8.astype(np.float32), axis=2)
    saturation = np.max(rgb_int16, axis=2) - np.min(rgb_int16, axis=2)
    background_mean = float(np.mean(background.color.astype(np.float32)))

    pale_background_like = (
        (brightness >= background_mean - float(options.pale_brightness_gap))
        & (saturation <= int(options.pale_max_saturation))
        & (color_distance <= background.tolerance + int(options.pale_extra_color_tolerance))
        & (color_cast_distance <= background.color_cast_tolerance + int(options.pale_extra_cast_tolerance))
    )
    strong_foreground = (
        (
            (color_distance >= background.tolerance + int(options.strong_color_margin))
            | (color_cast_distance >= background.color_cast_tolerance + int(options.strong_cast_margin))
        )
        & (saturation >= int(options.strong_saturation_floor))
    ) | (brightness <= background_mean - float(options.very_dark_brightness_gap))
    candidate_foreground = (
        (
            (color_distance >= background.tolerance + int(options.candidate_color_margin))
            | (color_cast_distance >= background.color_cast_tolerance + int(options.candidate_cast_margin))
        )
        & (saturation >= int(options.candidate_saturation_floor))
    ) | (brightness <= background_mean - float(options.very_dark_brightness_gap))

    seed_mask = strong_foreground & (~pale_background_like)
    if not np.any(seed_mask):
        return np.zeros(rgb_uint8.shape[:2], dtype=bool)

    candidate_mask = candidate_foreground & (~pale_background_like)
    connected = grow_mask_from_seed(
        candidate_mask=candidate_mask,
        seed_mask=seed_mask,
        connectivity=8,
    )
    trimmed = _trim_pale_boundary(
        np.asarray(connected, dtype=bool),
        rgb=rgb_uint8,
        background=background,
        options=options,
    )
    return _trim_pale_components_without_colored_anchor(
        trimmed,
        rgb=rgb_uint8,
        options=options,
    )


def _compact_boundary_colors(
    rgb: np.ndarray,
    *,
    core_mask: np.ndarray,
    background: BackgroundEstimate,
    options: ForegroundReconstructionOptions,
) -> np.ndarray:
    result = np.asarray(rgb, dtype=np.uint8).copy()
    occupied = np.asarray(core_mask, dtype=bool)
    if not np.any(occupied):
        return result

    boundary_mask = occupied & (_count_neighbors(occupied) < 8)
    if not np.any(boundary_mask):
        return result

    support_mask = _erode_mask(occupied, steps=1)
    if not np.any(support_mask):
        support_mask = occupied & (~boundary_mask)
    if not np.any(support_mask):
        return result

    support_rgb = _estimate_nearest_support_colors(
        result,
        target_mask=boundary_mask,
        support_mask=support_mask,
        radius=options.support_radius,
    )
    rgb_int16 = result.astype(np.int16)
    support_int16 = support_rgb.astype(np.int16)
    color_distance = _color_distance(rgb_int16, background.color)
    color_cast_distance = _color_cast_distance(rgb_int16, background.color)
    brightness = np.mean(result.astype(np.float32), axis=2)
    support_brightness = np.mean(support_rgb.astype(np.float32), axis=2)
    saturation = np.max(rgb_int16, axis=2) - np.min(rgb_int16, axis=2)
    distance_to_support = np.max(np.abs(rgb_int16 - support_int16), axis=2)

    recolor_mask = (
        boundary_mask
        & (brightness >= support_brightness + float(options.boundary_recolor_brightness_gap))
        & (saturation <= int(options.boundary_recolor_saturation_ceiling))
        & (distance_to_support >= int(options.support_recolor_distance_floor))
    )
    result[recolor_mask] = support_rgb[recolor_mask]
    return result


def _trim_pale_boundary(
    mask: np.ndarray,
    *,
    rgb: np.ndarray,
    background: BackgroundEstimate,
    options: ForegroundReconstructionOptions,
) -> np.ndarray:
    trimmed = np.asarray(mask, dtype=bool).copy()
    if not np.any(trimmed):
        return trimmed

    rgb_uint8 = np.asarray(rgb, dtype=np.uint8)
    rgb_int16 = rgb_uint8.astype(np.int16)
    color_distance = _color_distance(rgb_int16, background.color)
    color_cast_distance = _color_cast_distance(rgb_int16, background.color)
    brightness = np.mean(rgb_uint8.astype(np.float32), axis=2)
    saturation = np.max(rgb_int16, axis=2) - np.min(rgb_int16, axis=2)
    background_mean = float(np.mean(background.color.astype(np.float32)))
    pale_background_like = (
        (brightness >= background_mean - float(options.pale_brightness_gap))
        & (saturation <= int(options.pale_max_saturation))
        & (color_distance <= background.tolerance + int(options.pale_extra_color_tolerance))
        & (color_cast_distance <= background.color_cast_tolerance + int(options.pale_extra_cast_tolerance))
    )

    for _ in range(max(0, int(options.boundary_trim_iterations))):
        if not np.any(trimmed):
            break
        boundary_mask = trimmed & (_count_neighbors(trimmed) <= int(options.boundary_trim_neighbor_limit))
        removable_mask = boundary_mask & pale_background_like
        if not np.any(removable_mask):
            break
        trimmed[removable_mask] = False
    return trimmed


def _trim_pale_components_without_colored_anchor(
    mask: np.ndarray,
    *,
    rgb: np.ndarray,
    options: ForegroundReconstructionOptions,
) -> np.ndarray:
    trimmed = np.asarray(mask, dtype=bool).copy()
    if not np.any(trimmed):
        return trimmed

    rgb_uint8 = np.asarray(rgb, dtype=np.uint8)
    rgb_int16 = rgb_uint8.astype(np.int16)
    saturation = np.max(rgb_int16, axis=2) - np.min(rgb_int16, axis=2)
    for _ in range(max(0, int(options.pale_component_trim_iterations))):
        if not np.any(trimmed):
            break
        boundary_mask = trimmed & (_count_neighbors(trimmed) <= int(options.boundary_trim_neighbor_limit))
        removable_mask = boundary_mask & (saturation < int(options.pale_component_min_saturation))
        if not np.any(removable_mask):
            break
        trimmed[removable_mask] = False
    return trimmed


def _restore_enclosed_fill_regions(
    core_mask: np.ndarray,
    *,
    rgb: np.ndarray,
    background: BackgroundEstimate,
    options: ForegroundReconstructionOptions,
) -> np.ndarray:
    foreground = np.asarray(core_mask, dtype=bool)
    if not np.any(foreground):
        return np.zeros(foreground.shape, dtype=bool)

    close_kernel = max(1, int(options.enclosed_fill_close_kernel))
    closed_foreground = morphology_close(
        foreground,
        kernel_width=close_kernel,
        kernel_height=close_kernel,
    )
    border_connected_background = flood_mask_from_border(~closed_foreground, connectivity=4)
    enclosed_mask = (~closed_foreground) & (~border_connected_background)
    if not np.any(enclosed_mask):
        return np.zeros(foreground.shape, dtype=bool)

    rgb_uint8 = np.asarray(rgb, dtype=np.uint8)
    rgb_int16 = rgb_uint8.astype(np.int16)
    color_distance = _color_distance(rgb_int16, background.color)
    color_cast_distance = _color_cast_distance(rgb_int16, background.color)
    brightness = np.mean(rgb_uint8.astype(np.float32), axis=2)
    background_mean = float(np.mean(background.color.astype(np.float32)))
    height, width = enclosed_mask.shape
    result = np.zeros(enclosed_mask.shape, dtype=bool)
    for component in find_mask_components(enclosed_mask, connectivity=8):
        left = int(component["left"])
        top = int(component["top"])
        right = int(component["right"])
        bottom = int(component["bottom"])
        if left <= 0 or top <= 0 or right >= width or bottom >= height:
            continue

        area = int(component["area"])
        component_width = max(1, right - left)
        component_height = max(1, bottom - top)
        min_side = min(component_width, component_height)
        bbox_area = max(1, component_width * component_height)
        fill_ratio = float(area) / float(bbox_area)
        if area < int(options.enclosed_fill_min_area) or min_side < int(options.enclosed_fill_min_side):
            continue
        if fill_ratio < float(options.enclosed_fill_fill_ratio):
            continue

        local_mask = np.asarray(component["mask"], dtype=bool)
        component_color_distance = color_distance[top:bottom, left:right][local_mask]
        component_cast_distance = color_cast_distance[top:bottom, left:right][local_mask]
        component_brightness = brightness[top:bottom, left:right][local_mask]
        if component_color_distance.size == 0:
            continue
        if (
            np.percentile(component_color_distance, 60) < int(options.enclosed_fill_min_color_distance)
            and np.percentile(component_cast_distance, 60) < int(options.enclosed_fill_min_cast_distance)
            and np.percentile(component_brightness, 60) > background_mean - float(options.enclosed_fill_max_brightness_gap)
        ):
            continue
        result[top:bottom, left:right][local_mask] = True
    return result


def _estimate_nearest_support_colors(
    rgb: np.ndarray,
    *,
    target_mask: np.ndarray,
    support_mask: np.ndarray,
    radius: int,
) -> np.ndarray:
    result = np.asarray(rgb, dtype=np.uint8).copy()
    target = np.asarray(target_mask, dtype=bool)
    support = np.asarray(support_mask, dtype=bool)
    if not np.any(target) or not np.any(support):
        return result

    height, width = target.shape
    resolved_radius = max(1, int(radius))
    padded_rgb = np.pad(
        result,
        ((resolved_radius, resolved_radius), (resolved_radius, resolved_radius), (0, 0)),
        mode="edge",
    )
    padded_support = np.pad(support, resolved_radius, mode="constant", constant_values=False)
    best_distance = np.full(target.shape, resolved_radius * resolved_radius + 1, dtype=np.int16)

    for dy in range(-resolved_radius, resolved_radius + 1):
        for dx in range(-resolved_radius, resolved_radius + 1):
            distance = dy * dy + dx * dx
            if distance > resolved_radius * resolved_radius:
                continue
            top = resolved_radius + dy
            left = resolved_radius + dx
            candidate_mask = padded_support[top : top + height, left : left + width]
            update_mask = target & candidate_mask & (distance < best_distance)
            if not np.any(update_mask):
                continue
            candidate_rgb = padded_rgb[top : top + height, left : left + width]
            result[update_mask] = candidate_rgb[update_mask]
            best_distance[update_mask] = distance
    return result


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


def _erode_mask(mask: np.ndarray, *, steps: int) -> np.ndarray:
    result = np.asarray(mask, dtype=bool).copy()
    for _ in range(max(0, int(steps))):
        padded = np.pad(result, 1, mode="constant", constant_values=False)
        eroded = np.ones_like(result)
        for offset_y in range(3):
            for offset_x in range(3):
                eroded &= padded[offset_y : offset_y + result.shape[0], offset_x : offset_x + result.shape[1]]
        result = eroded
        if not np.any(result):
            return np.zeros(mask.shape, dtype=bool)
    return result


def _count_neighbors(mask: np.ndarray) -> np.ndarray:
    padded = np.pad(np.asarray(mask, dtype=np.uint8), 1, mode="constant", constant_values=0)
    count = np.zeros(mask.shape, dtype=np.uint8)
    for offset_y in range(3):
        for offset_x in range(3):
            if offset_y == 1 and offset_x == 1:
                continue
            count += padded[offset_y : offset_y + mask.shape[0], offset_x : offset_x + mask.shape[1]]
    return count
