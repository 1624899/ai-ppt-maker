from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class AlphaOuterEdgeTightenOptions:
    solid_threshold: int = 224
    shrink_ceiling: int = 248
    supported_scale: float = 0.38
    detached_scale: float = 0.16
    weak_alpha_cutoff: int = 96
    fragile_neighbor_limit: int = 2
    fragile_scale: float = 0.08


@dataclass(frozen=True)
class AlphaBackgroundFringeRemovalOptions:
    iterations: int = 2
    alpha_ceiling: int = 255
    weak_alpha_ceiling: int = 192


DEFAULT_ALPHA_OUTER_EDGE_TIGHTEN_OPTIONS = AlphaOuterEdgeTightenOptions()
DEFAULT_ALPHA_BACKGROUND_FRINGE_REMOVAL_OPTIONS = AlphaBackgroundFringeRemovalOptions()


def remove_outer_background_like_fringe(
    alpha: np.ndarray,
    *,
    background_like_mask: np.ndarray,
    protected_mask: np.ndarray | None = None,
    options: AlphaBackgroundFringeRemovalOptions = DEFAULT_ALPHA_BACKGROUND_FRINGE_REMOVAL_OPTIONS,
) -> np.ndarray:
    """直接清掉最外圈像背景的残留像素，优先换取干净边界。"""
    source = np.asarray(alpha, dtype=np.uint8)
    if source.ndim != 2 or source.size == 0:
        return np.array(source, copy=True)

    background_like = np.asarray(background_like_mask, dtype=bool)
    if background_like.shape != source.shape:
        return np.array(source, copy=True)

    protected = np.zeros(source.shape, dtype=bool)
    if protected_mask is not None:
        resolved_protected = np.asarray(protected_mask, dtype=bool)
        if resolved_protected.shape == source.shape:
            protected = resolved_protected

    result = np.array(source, copy=True)
    candidate_base = background_like & (~protected)
    if not np.any(candidate_base):
        return result

    for _ in range(max(0, int(options.iterations))):
        occupied_mask = result > 0
        if not np.any(occupied_mask):
            break

        neighbor_count = _count_neighbors(occupied_mask)
        outer_edge_mask = occupied_mask & (neighbor_count < 8)
        removable_mask = (
            outer_edge_mask
            & candidate_base
            & (
                (result <= int(options.alpha_ceiling))
                | ((result <= int(options.weak_alpha_ceiling)) & (neighbor_count <= 5))
            )
        )
        if not np.any(removable_mask):
            break

        result[removable_mask] = 0
    return result


def tighten_outer_alpha_fringe(
    alpha: np.ndarray,
    *,
    protected_mask: np.ndarray | None = None,
    options: AlphaOuterEdgeTightenOptions = DEFAULT_ALPHA_OUTER_EDGE_TIGHTEN_OPTIONS,
) -> np.ndarray:
    """收紧最外圈 alpha，削弱偏厚偏糙的边缘，同时尽量保留主体硬边。"""
    source = np.asarray(alpha, dtype=np.uint8)
    if source.ndim != 2 or source.size == 0:
        return np.array(source, copy=True)

    occupied_mask = source > 0
    if not np.any(occupied_mask):
        return np.array(source, copy=True)

    protected = np.zeros(source.shape, dtype=bool)
    if protected_mask is not None:
        resolved_protected = np.asarray(protected_mask, dtype=bool)
        if resolved_protected.shape == source.shape:
            protected = resolved_protected

    edge_mask = occupied_mask & (_count_neighbors(occupied_mask) < 8)
    shrinkable_mask = edge_mask & (source < int(options.shrink_ceiling)) & (~protected)
    if not np.any(shrinkable_mask):
        return np.array(source, copy=True)

    solid_mask = source >= int(options.solid_threshold)
    solid_support_mask = _dilate_mask(solid_mask, steps=1)
    opposite_support_mask = _has_opposite_pairs(occupied_mask)
    neighbor_count = _count_neighbors(occupied_mask)

    supported_edge_mask = shrinkable_mask & solid_support_mask
    detached_edge_mask = shrinkable_mask & (~solid_support_mask)
    fragile_edge_mask = supported_edge_mask & (~opposite_support_mask) & (
        neighbor_count <= int(options.fragile_neighbor_limit)
    )

    result = np.array(source, copy=True)
    result[supported_edge_mask] = _scale_alpha(
        result[supported_edge_mask],
        scale=float(options.supported_scale),
    )
    result[detached_edge_mask] = _scale_alpha(
        result[detached_edge_mask],
        scale=float(options.detached_scale),
    )
    result[fragile_edge_mask] = _scale_alpha(
        result[fragile_edge_mask],
        scale=float(options.fragile_scale),
    )

    removable_mask = (
        (detached_edge_mask | fragile_edge_mask)
        & (source <= int(options.weak_alpha_cutoff))
    )
    result[removable_mask] = 0
    return result


def _scale_alpha(values: np.ndarray, *, scale: float) -> np.ndarray:
    scaled = np.round(values.astype(np.float32) * max(0.0, float(scale)))
    return np.clip(scaled, 0, 255).astype(np.uint8)


def _count_neighbors(mask: np.ndarray) -> np.ndarray:
    padded = np.pad(np.asarray(mask, dtype=np.uint8), 1, mode="constant", constant_values=0)
    count = np.zeros(mask.shape, dtype=np.uint8)
    for offset_y in range(3):
        for offset_x in range(3):
            if offset_y == 1 and offset_x == 1:
                continue
            count += padded[offset_y : offset_y + mask.shape[0], offset_x : offset_x + mask.shape[1]]
    return count


def _dilate_mask(mask: np.ndarray, *, steps: int) -> np.ndarray:
    result = np.asarray(mask, dtype=bool).copy()
    for _ in range(max(0, int(steps))):
        padded = np.pad(result, 1, mode="constant", constant_values=False)
        expanded = np.zeros_like(result)
        for offset_y in range(3):
            for offset_x in range(3):
                expanded |= padded[offset_y : offset_y + result.shape[0], offset_x : offset_x + result.shape[1]]
        result = expanded
    return result


def _has_opposite_pairs(mask: np.ndarray) -> np.ndarray:
    source = np.asarray(mask, dtype=bool)
    padded = np.pad(source, 1, mode="constant", constant_values=False)
    up = padded[0 : source.shape[0], 1 : source.shape[1] + 1]
    down = padded[2 : source.shape[0] + 2, 1 : source.shape[1] + 1]
    left = padded[1 : source.shape[0] + 1, 0 : source.shape[1]]
    right = padded[1 : source.shape[0] + 1, 2 : source.shape[1] + 2]
    up_left = padded[0 : source.shape[0], 0 : source.shape[1]]
    up_right = padded[0 : source.shape[0], 2 : source.shape[1] + 2]
    down_left = padded[2 : source.shape[0] + 2, 0 : source.shape[1]]
    down_right = padded[2 : source.shape[0] + 2, 2 : source.shape[1] + 2]
    return (up & down) | (left & right) | (up_left & down_right) | (up_right & down_left)
