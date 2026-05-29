from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ppt_system.binary_morphology import morphology_close
from ppt_system.cv_mask_components import find_mask_components


@dataclass(frozen=True)
class FillRegionComponent:
    left: int
    top: int
    right: int
    bottom: int
    mask: np.ndarray
    core_mask: np.ndarray
    boundary_mask: np.ndarray
    reference_rgb: np.ndarray
    reference_alpha: int


@dataclass(frozen=True)
class FillRegionAnalysis:
    full_mask: np.ndarray
    core_mask: np.ndarray
    boundary_mask: np.ndarray
    components: tuple[FillRegionComponent, ...]


def analyze_fill_regions(
    source_rgb: np.ndarray,
    alpha: np.ndarray,
    *,
    background_color: np.ndarray,
) -> FillRegionAnalysis:
    """识别应从边缘去污链路中保护出来的真实填充块。"""
    rgb = np.asarray(source_rgb, dtype=np.uint8)
    resolved_alpha = np.asarray(alpha, dtype=np.uint8)
    if rgb.ndim != 3 or rgb.shape[2] != 3 or resolved_alpha.ndim != 2:
        return _empty_fill_region_analysis(resolved_alpha.shape if resolved_alpha.ndim == 2 else rgb.shape[:2])

    candidate_mask = _build_fill_candidate_mask(
        rgb,
        resolved_alpha,
        background_color=np.asarray(background_color, dtype=np.int16),
    )
    if not np.any(candidate_mask):
        return _empty_fill_region_analysis(resolved_alpha.shape)

    candidate_mask = morphology_close(candidate_mask, kernel_width=3, kernel_height=3)
    height, width = resolved_alpha.shape
    full_mask = np.zeros((height, width), dtype=bool)
    core_mask = np.zeros((height, width), dtype=bool)
    boundary_mask = np.zeros((height, width), dtype=bool)
    components: list[FillRegionComponent] = []

    for component in find_mask_components(candidate_mask, connectivity=8):
        left = int(component["left"])
        top = int(component["top"])
        right = int(component["right"])
        bottom = int(component["bottom"])
        if left <= 0 or top <= 0 or right >= width or bottom >= height:
            continue

        raw_local_mask = np.asarray(component["mask"], dtype=bool)
        area = int(component["area"])
        component_width = max(1, right - left)
        component_height = max(1, bottom - top)
        bbox_area = max(1, component_width * component_height)
        fill_ratio = float(area) / float(bbox_area)
        min_side = min(component_width, component_height)
        if area < 64 or min_side < 6:
            continue
        if fill_ratio < 0.34 and not (area >= 144 and min_side >= 8 and fill_ratio >= 0.26):
            continue

        source_crop = rgb[top:bottom, left:right]
        alpha_crop = resolved_alpha[top:bottom, left:right]
        local_mask = _build_protected_local_mask(
            raw_local_mask,
            component_width=component_width,
            component_height=component_height,
        )
        protected_area = int(np.count_nonzero(local_mask))
        if protected_area <= 0:
            continue
        protected_fill_ratio = float(protected_area) / float(bbox_area)
        if protected_fill_ratio >= 0.92 and fill_ratio <= 0.22:
            continue

        core_local_mask = _build_fill_core_mask(
            local_mask,
            component_width=component_width,
            component_height=component_height,
            protected_area=protected_area,
        )
        boundary_local_mask = local_mask & (~core_local_mask)

        reference_rgb = _estimate_reference_rgb(
            source_crop,
            local_mask=local_mask,
            core_local_mask=core_local_mask,
        )
        component_pixels = source_crop[local_mask].astype(np.int16)
        distance_to_reference = np.max(
            np.abs(component_pixels - reference_rgb.reshape(1, 3).astype(np.int16)),
            axis=1,
        )
        if np.percentile(distance_to_reference, 80) > 30:
            continue
        reference_alpha = _estimate_reference_alpha(
            alpha_crop,
            local_mask=local_mask,
            core_local_mask=core_local_mask,
        )

        full_mask[top:bottom, left:right][local_mask] = True
        core_mask[top:bottom, left:right][core_local_mask] = True
        boundary_mask[top:bottom, left:right][boundary_local_mask] = True
        components.append(
            FillRegionComponent(
                left=left,
                top=top,
                right=right,
                bottom=bottom,
                mask=local_mask,
                core_mask=core_local_mask,
                boundary_mask=boundary_local_mask,
                reference_rgb=reference_rgb.astype(np.uint8),
                reference_alpha=reference_alpha,
            )
        )

    return FillRegionAnalysis(
        full_mask=full_mask,
        core_mask=core_mask,
        boundary_mask=boundary_mask,
        components=tuple(components),
    )


def protect_fill_region_alpha(
    alpha: np.ndarray,
    *,
    analysis: FillRegionAnalysis,
) -> np.ndarray:
    """对识别出的真实填充块核心建立 alpha 保护地板，边界仍交给清边流程。"""
    protected_alpha = np.array(alpha, copy=True).astype(np.uint8)
    if not analysis.components:
        return protected_alpha

    for component in analysis.components:
        top = component.top
        bottom = component.bottom
        left = component.left
        right = component.right
        alpha_crop = protected_alpha[top:bottom, left:right]
        local_mask = component.core_mask if np.any(component.core_mask) else component.mask
        if not np.any(local_mask):
            continue
        alpha_crop[local_mask] = np.maximum(alpha_crop[local_mask], np.uint8(component.reference_alpha))
        protected_alpha[top:bottom, left:right] = alpha_crop
    return protected_alpha


def purify_fill_region_artifacts(
    source_rgb: np.ndarray,
    rgb: np.ndarray,
    alpha: np.ndarray,
    *,
    analysis: FillRegionAnalysis,
) -> tuple[np.ndarray, np.ndarray]:
    """恢复真实填充块核心颜色，避免边缘去污把大块填充处理脏。"""
    resolved_source = np.asarray(source_rgb, dtype=np.uint8)
    result_rgb = np.array(rgb, copy=True).astype(np.float32)
    result_alpha = np.array(alpha, copy=True).astype(np.uint8)
    if not analysis.components:
        return np.clip(result_rgb, 0.0, 255.0).astype(np.uint8), result_alpha

    for component in analysis.components:
        top = component.top
        bottom = component.bottom
        left = component.left
        right = component.right
        local_mask = component.core_mask if np.any(component.core_mask) else component.mask
        source_crop = resolved_source[top:bottom, left:right].astype(np.float32)
        rgb_crop = result_rgb[top:bottom, left:right]
        rgb_crop[local_mask] = source_crop[local_mask]
        result_rgb[top:bottom, left:right] = rgb_crop
        alpha_crop = result_alpha[top:bottom, left:right]
        alpha_crop[local_mask] = np.maximum(alpha_crop[local_mask], np.uint8(component.reference_alpha))
        result_alpha[top:bottom, left:right] = alpha_crop

    return np.clip(result_rgb, 0.0, 255.0).astype(np.uint8), result_alpha


def clean_fill_region_boundary_fringe(
    rgb: np.ndarray,
    alpha: np.ndarray,
    *,
    analysis: FillRegionAnalysis,
    background_color: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """清掉真实填充块边界上的背景色亮边，同时保留明显描边。"""
    result_rgb = np.array(rgb, copy=True).astype(np.uint8)
    result_alpha = np.array(alpha, copy=True).astype(np.uint8)
    if not analysis.components:
        return result_rgb, result_alpha

    background = np.asarray(background_color, dtype=np.int16).reshape(1, 3)
    for component in analysis.components:
        top = component.top
        bottom = component.bottom
        left = component.left
        right = component.right
        boundary_mask = np.asarray(component.boundary_mask, dtype=bool)
        if not np.any(boundary_mask):
            continue

        rgb_crop = result_rgb[top:bottom, left:right]
        alpha_crop = result_alpha[top:bottom, left:right]
        source_int16 = rgb_crop.astype(np.int16)
        boundary_pixels = source_int16[boundary_mask]
        reference = component.reference_rgb.astype(np.int16).reshape(1, 3)
        distance_to_background = np.max(np.abs(boundary_pixels - background), axis=1)
        distance_to_reference = np.max(np.abs(boundary_pixels - reference), axis=1)
        brightness = np.mean(boundary_pixels.astype(np.float32), axis=1)
        background_brightness = float(np.mean(background.astype(np.float32)))

        removable_values = (
            (distance_to_background <= 22)
            | ((distance_to_reference <= 18) & (brightness >= background_brightness - 26.0))
            | ((distance_to_reference <= 26) & (brightness >= background_brightness - 18.0))
        )
        removable_mask = np.zeros(boundary_mask.shape, dtype=bool)
        removable_mask[boundary_mask] = removable_values
        if not np.any(removable_mask):
            continue

        alpha_crop[removable_mask] = 0
        result_alpha[top:bottom, left:right] = alpha_crop
        result_rgb[top:bottom, left:right] = rgb_crop

    return result_rgb, result_alpha


def _empty_fill_region_analysis(shape: tuple[int, int]) -> FillRegionAnalysis:
    height, width = shape
    empty_mask = np.zeros((height, width), dtype=bool)
    return FillRegionAnalysis(
        full_mask=empty_mask,
        core_mask=np.zeros((height, width), dtype=bool),
        boundary_mask=np.zeros((height, width), dtype=bool),
        components=tuple(),
    )


def _build_fill_candidate_mask(
    rgb: np.ndarray,
    alpha: np.ndarray,
    *,
    background_color: np.ndarray,
) -> np.ndarray:
    rgb_int16 = rgb.astype(np.int16)
    rgb_float = rgb.astype(np.float32)
    brightness = np.mean(rgb_float, axis=2)
    saturation = np.max(rgb_int16, axis=2) - np.min(rgb_int16, axis=2)
    background_mean = float(np.mean(background_color.astype(np.float32)))
    background_distance = np.max(
        np.abs(rgb_int16 - background_color.reshape(1, 1, 3)),
        axis=2,
    )
    return (
        (alpha >= 48)
        & (brightness >= max(132.0, background_mean - 120.0))
        & (saturation <= 112)
        & ((background_distance >= 4) | (alpha >= 180))
    )


def _estimate_reference_rgb(
    rgb_crop: np.ndarray,
    *,
    local_mask: np.ndarray,
    core_local_mask: np.ndarray,
) -> np.ndarray:
    reference_mask = core_local_mask if np.any(core_local_mask) else local_mask
    reference_pixels = rgb_crop[reference_mask]
    if reference_pixels.size == 0:
        return np.array([255, 255, 255], dtype=np.uint8)

    reference_float = reference_pixels.astype(np.float32)
    brightness = np.mean(reference_float, axis=1)
    brightness_floor = float(np.percentile(brightness, 35)) if brightness.size >= 8 else float(np.min(brightness))
    filtered_pixels = reference_pixels[brightness >= brightness_floor]
    if filtered_pixels.size == 0:
        filtered_pixels = reference_pixels
    return np.round(np.median(filtered_pixels.astype(np.float32), axis=0)).astype(np.uint8)


def _estimate_reference_alpha(
    alpha_crop: np.ndarray,
    *,
    local_mask: np.ndarray,
    core_local_mask: np.ndarray,
) -> int:
    reference_mask = core_local_mask if np.any(core_local_mask) else local_mask
    reference_alpha = alpha_crop[reference_mask]
    if reference_alpha.size == 0:
        return 0
    resolved = int(np.round(np.percentile(reference_alpha.astype(np.float32), 60)))
    return max(32, min(224, resolved))


def _build_protected_local_mask(
    local_mask: np.ndarray,
    *,
    component_width: int,
    component_height: int,
) -> np.ndarray:
    if not np.any(local_mask):
        return np.zeros(local_mask.shape, dtype=bool)

    kernel_width = 3
    kernel_height = 3
    if component_width >= 12:
        kernel_width = 5
    if component_width >= 24:
        kernel_width = 7
    if component_height >= 12:
        kernel_height = 5
    if component_height >= 24:
        kernel_height = 7
    protected = morphology_close(
        local_mask,
        kernel_width=kernel_width,
        kernel_height=kernel_height,
    )
    return _fill_enclosed_holes(np.asarray(protected, dtype=bool))


def _build_fill_core_mask(
    local_mask: np.ndarray,
    *,
    component_width: int,
    component_height: int,
    protected_area: int,
) -> np.ndarray:
    min_side = min(int(component_width), int(component_height))
    erode_steps = 2 if min_side >= 10 else 1
    core = _erode_mask(local_mask, steps=erode_steps)
    if np.count_nonzero(core) >= max(12, int(protected_area) // 5):
        return core

    fallback_core = _erode_mask(local_mask, steps=1)
    if np.count_nonzero(fallback_core) >= max(12, int(protected_area) // 5):
        return fallback_core
    return np.array(local_mask, copy=True)


def _erode_mask(mask: np.ndarray, *, steps: int) -> np.ndarray:
    result = np.asarray(mask, dtype=bool)
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


def _max_channel_distance(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    return np.max(
        np.abs(first.astype(np.float32) - second.astype(np.float32)),
        axis=2,
    )


def _fill_enclosed_holes(mask: np.ndarray) -> np.ndarray:
    source = np.asarray(mask, dtype=bool)
    if not np.any(source):
        return np.zeros(source.shape, dtype=bool)

    inverse = ~source
    padded = np.pad(inverse, 1, mode="constant", constant_values=True)
    visited = np.zeros_like(padded, dtype=bool)
    stack: list[tuple[int, int]] = [(0, 0)]
    visited[0, 0] = True

    while stack:
        y, x = stack.pop()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny = y + dy
            nx = x + dx
            if not (0 <= ny < padded.shape[0] and 0 <= nx < padded.shape[1]):
                continue
            if visited[ny, nx] or not padded[ny, nx]:
                continue
            visited[ny, nx] = True
            stack.append((ny, nx))

    hole_mask = padded & (~visited)
    filled = np.array(source, copy=True)
    filled |= hole_mask[1:-1, 1:-1]
    return filled
