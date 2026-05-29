from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from PIL import Image
from ppt_system.alpha_fill_region_cleanup import (
    analyze_fill_regions,
    clean_fill_region_boundary_fringe,
    protect_fill_region_alpha,
    purify_fill_region_artifacts,
)
from ppt_system.cv_mask_components import find_mask_components
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
    """统一精修去背结果，提升 alpha 连续性并减少白边污染。"""
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
    height, width = rgba.shape[:2]
    rgb = rgba[:, :, :3].astype(np.int16)
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
    rgb = source_rgba[:, :, :3].astype(np.int16)
    color_distance = _color_distance(rgb, background.color)
    color_cast_distance = _color_cast_distance(rgb, background.color)
    soft_band = max(12, min(56, int(background.tolerance * 1.6)))
    fade_start = max(0.0, float(background.tolerance) - min(8.0, float(background.tolerance) * 0.35))
    effective_distance = np.maximum(color_distance, color_cast_distance * 2)
    alpha_scale = np.clip((effective_distance.astype(np.float32) - fade_start) / float(soft_band), 0.0, 1.0)
    guided_alpha = np.round(alpha_scale * 255.0).astype(np.uint8)
    hard_background = _background_like_mask(
        rgb,
        background=background,
        extra_color_tolerance=4,
        extra_cast_tolerance=0,
    ) & _bright_background_mask(rgb, 245)
    external_hard_background = _flood_fill_from_border(hard_background)
    guided_alpha[external_hard_background] = 0
    return guided_alpha
def refine_alpha_matte(
    source_rgba: np.ndarray,
    removed_rgba: np.ndarray,
    *,
    background: BackgroundModel,
) -> np.ndarray:
    result = np.array(removed_rgba, copy=True)
    initial_alpha = removed_rgba[:, :, 3].astype(np.uint8)
    guided_alpha = build_color_guided_alpha(source_rgba, background=background)
    rgb = source_rgba[:, :, :3].astype(np.int16)
    color_distance = _color_distance(rgb, background.color)
    color_cast_distance = _color_cast_distance(rgb, background.color)
    near_background_fill = _background_like_mask(
        rgb,
        background=background,
        extra_color_tolerance=10,
        extra_cast_tolerance=2,
    )
    guided_revival_allowed = ~near_background_fill
    initial_alpha_for_refine = initial_alpha
    strong_colored_foreground = (
        (color_distance >= background.tolerance + max(18, background.tolerance // 3))
        | (color_cast_distance >= background.color_cast_tolerance + 4)
    )
    supported_light_edge = near_background_fill & _dilate_mask(strong_colored_foreground, steps=1)
    removable_light_fill = near_background_fill & (~supported_light_edge)
    initial_alpha_for_refine = np.where(removable_light_fill, 0, initial_alpha).astype(np.uint8)
    base_alpha = np.where(
        initial_alpha_for_refine > 0,
        initial_alpha_for_refine,
        np.where(guided_revival_allowed, guided_alpha, 0),
    ).astype(np.uint8)
    strong_foreground = (
        (base_alpha >= 200)
        | (color_distance >= background.tolerance + max(18, background.tolerance // 3))
    )
    candidate_foreground = (
        (base_alpha >= 10)
        | (color_distance >= max(8, background.tolerance - 8))
        | (color_cast_distance >= background.color_cast_tolerance + 2)
    )
    connected_foreground = _grow_from_seeds(
        candidate_mask=candidate_foreground,
        seed_mask=strong_foreground,
    )
    support_mask = _dilate_mask(connected_foreground, steps=1)
    supported_alpha = np.where(support_mask, base_alpha, 0).astype(np.uint8)
    initial_fill_region_analysis = analyze_fill_regions(
        source_rgba[:, :, :3],
        supported_alpha,
        background_color=background.color,
    )
    protected_supported_alpha = protect_fill_region_alpha(
        supported_alpha,
        analysis=initial_fill_region_analysis,
    )
    promoted_alpha = _promote_supported_soft_edges(
        alpha=protected_supported_alpha,
        connected_mask=connected_foreground,
        color_distance=color_distance,
        tolerance=background.tolerance,
    )
    bridged_alpha = _bridge_narrow_gaps(
        alpha=promoted_alpha,
        color_distance=color_distance,
        tolerance=background.tolerance,
    )
    suppressed_alpha = _suppress_weak_white_fringe(
        alpha=bridged_alpha,
        rgb=rgb,
        background=background,
        protected_mask=initial_fill_region_analysis.core_mask,
    )
    tightened_alpha = _tighten_background_like_edge_alpha(
        alpha=suppressed_alpha,
        rgb=rgb,
        background=background,
        protected_mask=initial_fill_region_analysis.core_mask,
    )
    smoothed_alpha = _smooth_transition_alpha(
        tightened_alpha,
        locked_mask=(tightened_alpha >= 240) | (~support_mask) | initial_fill_region_analysis.full_mask,
        iterations=1,
    )
    fill_region_analysis = analyze_fill_regions(
        source_rgba[:, :, :3],
        smoothed_alpha,
        background_color=background.color,
    )
    protected_smoothed_alpha = protect_fill_region_alpha(
        smoothed_alpha,
        analysis=fill_region_analysis,
    )
    cleaned_rgb, cleaned_alpha = _clean_bright_outline_residue(
        rgb=source_rgba[:, :, :3],
        alpha=protected_smoothed_alpha,
        background=background,
        protected_mask=fill_region_analysis.core_mask,
    )
    decontaminated_rgb = _decontaminate_edge_colors(
        cleaned_rgb,
        alpha=cleaned_alpha,
        background=background,
        protected_mask=fill_region_analysis.core_mask,
    )
    sharpened_rgb, sharpened_alpha = _sharpen_supported_edge_detail(
        rgb=decontaminated_rgb,
        alpha=cleaned_alpha,
        background=background,
        protected_mask=fill_region_analysis.core_mask,
    )
    purified_rgb, purified_alpha = purify_fill_region_artifacts(
        source_rgba[:, :, :3],
        sharpened_rgb,
        sharpened_alpha,
        analysis=fill_region_analysis,
    )
    purified_rgb, purified_alpha = clean_fill_region_boundary_fringe(
        purified_rgb,
        purified_alpha,
        analysis=fill_region_analysis,
        background_color=background.color,
    )
    result[:, :, :3] = purified_rgb
    result[:, :, 3] = purified_alpha
    return result
def _bright_background_mask(rgb: np.ndarray, fallback_bg_threshold: int) -> np.ndarray:
    return (
        (rgb[:, :, 0] >= fallback_bg_threshold)
        & (rgb[:, :, 1] >= fallback_bg_threshold)
        & (rgb[:, :, 2] >= fallback_bg_threshold)
    )
def _clean_final_background_like_outer_fringe(
    *,
    alpha: np.ndarray,
    rgb: np.ndarray,
    background: BackgroundModel,
    protected_mask: np.ndarray | None = None,
) -> np.ndarray:
    """最后统一切掉最外圈背景色残留，避免前面步骤留下断续浅边。"""
    rgb_int16 = np.asarray(rgb, dtype=np.int16)
    background_like = _background_like_mask(
        rgb_int16,
        background=background,
        extra_color_tolerance=22,
        extra_cast_tolerance=3,
    ) | (
        _pale_highlight_mask(
            rgb_int16,
            background=background,
        )
        & _dilate_mask(np.asarray(alpha, dtype=np.uint8) >= 160, steps=1)
    )
    return remove_outer_background_like_fringe(
        alpha,
        background_like_mask=background_like,
        protected_mask=protected_mask,
    )
def _pale_highlight_mask(
    rgb: np.ndarray,
    *,
    background: BackgroundModel,
) -> np.ndarray:
    rgb_float = rgb.astype(np.float32)
    brightness = np.mean(rgb_float, axis=2)
    channel_floor = np.min(rgb_float, axis=2)
    background_mean = float(np.mean(background.color))
    background_floor = float(np.min(background.color))
    return (
        (brightness >= max(196.0, background_mean - 56.0))
        & (channel_floor >= max(156.0, background_floor - 84.0))
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
def _background_like_mask(
    rgb: np.ndarray,
    *,
    background: BackgroundModel,
    extra_color_tolerance: int = 0,
    extra_cast_tolerance: int = 0,
) -> np.ndarray:
    color_distance = _color_distance(rgb, background.color)
    color_cast_distance = _color_cast_distance(rgb, background.color)
    return (
        (color_distance <= background.tolerance + int(extra_color_tolerance))
        & (color_cast_distance <= background.color_cast_tolerance + int(extra_cast_tolerance))
    )
def _grow_from_seeds(candidate_mask: np.ndarray, seed_mask: np.ndarray) -> np.ndarray:
    height, width = candidate_mask.shape
    visited = np.zeros((height, width), dtype=bool)
    queue: list[tuple[int, int]] = []
    ys, xs = np.nonzero(candidate_mask & seed_mask)
    for y, x in zip(ys.tolist(), xs.tolist()):
        visited[y, x] = True
        queue.append((y, x))
    cursor = 0
    while cursor < len(queue):
        y, x = queue[cursor]
        cursor += 1
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                ny = y + dy
                nx = x + dx
                if 0 <= ny < height and 0 <= nx < width and candidate_mask[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True
                    queue.append((ny, nx))
    return visited
def _dilate_mask(mask: np.ndarray, *, steps: int) -> np.ndarray:
    result = np.array(mask, copy=True)
    for _ in range(max(0, int(steps))):
        padded = np.pad(result, 1, mode="constant", constant_values=False)
        expanded = np.zeros_like(result)
        for offset_y in range(3):
            for offset_x in range(3):
                expanded |= padded[offset_y : offset_y + result.shape[0], offset_x : offset_x + result.shape[1]]
        result = expanded
    return result
def _promote_supported_soft_edges(
    *,
    alpha: np.ndarray,
    connected_mask: np.ndarray,
    color_distance: np.ndarray,
    tolerance: int,
) -> np.ndarray:
    promoted = np.array(alpha, copy=True)
    soft_edge_mask = connected_mask & (promoted > 0) & (promoted < 160)
    if not np.any(soft_edge_mask):
        return promoted
    boost_floor = np.clip((color_distance.astype(np.int16) - max(0, tolerance // 3)) * 4, 0, 192).astype(np.uint8)
    promoted[soft_edge_mask] = np.maximum(promoted[soft_edge_mask], boost_floor[soft_edge_mask])
    return promoted
def _bridge_narrow_gaps(
    *,
    alpha: np.ndarray,
    color_distance: np.ndarray,
    tolerance: int,
) -> np.ndarray:
    bridged = np.array(alpha, copy=True)
    solid_mask = bridged >= 160
    if not np.any(solid_mask):
        return bridged
    weak_candidate = (bridged == 0) & (color_distance >= max(10, tolerance - 2))
    if not np.any(weak_candidate):
        return bridged
    bridge_strength = np.clip((color_distance.astype(np.int16) - max(0, tolerance // 2)) * 4, 0, 224).astype(np.uint8)
    directional_pairs = (
        ((0, -1), (0, 1)),
        ((-1, 0), (1, 0)),
        ((-1, -1), (1, 1)),
        ((-1, 1), (1, -1)),
    )
    height, width = bridged.shape
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            if not weak_candidate[y, x]:
                continue
            for (dy0, dx0), (dy1, dx1) in directional_pairs:
                if solid_mask[y + dy0, x + dx0] and solid_mask[y + dy1, x + dx1]:
                    neighbor_alpha = max(
                        int(bridged[y + dy0, x + dx0]),
                        int(bridged[y + dy1, x + dx1]),
                    )
                    bridged[y, x] = max(
                        bridged[y, x],
                        min(neighbor_alpha, int(bridge_strength[y, x])),
                    )
                    break
    return bridged
def _suppress_weak_white_fringe(
    *,
    alpha: np.ndarray,
    rgb: np.ndarray,
    background: BackgroundModel,
    protected_mask: np.ndarray | None = None,
) -> np.ndarray:
    suppressed = np.array(alpha, copy=True)
    weak_background_mask = _background_like_mask(
        rgb,
        background=background,
        extra_color_tolerance=10,
        extra_cast_tolerance=1,
    )
    weak_white_mask = (
        (suppressed > 0)
        & (suppressed <= 72)
        & weak_background_mask
    )
    if not np.any(weak_white_mask):
        return suppressed
    support_count = _count_alpha_neighbors(suppressed > 0)
    orthogonal_strong_neighbor_count = _count_alpha_neighbors(
        suppressed >= 160,
        include_diagonal=False,
    )
    removable = weak_white_mask & (support_count <= 2) & (orthogonal_strong_neighbor_count == 0)
    if protected_mask is not None:
        removable &= ~np.asarray(protected_mask, dtype=bool)
    suppressed[removable] = 0
    return suppressed
def _tighten_background_like_edge_alpha(
    *,
    alpha: np.ndarray,
    rgb: np.ndarray,
    background: BackgroundModel,
    protected_mask: np.ndarray | None = None,
) -> np.ndarray:
    tightened = np.array(alpha, copy=True)
    edge_mask = (tightened > 0) & (tightened < 255)
    if not np.any(edge_mask):
        return tightened
    background_like = _background_like_mask(
        rgb,
        background=background,
        extra_color_tolerance=14,
        extra_cast_tolerance=1,
    )
    target_mask = edge_mask & background_like
    if protected_mask is not None:
        target_mask &= ~np.asarray(protected_mask, dtype=bool)
    target_mask = _limit_outline_cleanup_to_narrow_bands(
        target_mask=target_mask,
        occupied_mask=(tightened > 0),
    )
    if not np.any(target_mask):
        return tightened
    alpha_ratio = tightened.astype(np.float32) / 255.0
    color_distance = _color_distance(rgb, background.color).astype(np.float32)
    fade_span = max(8.0, float(background.tolerance) * 0.9)
    distance_weight = np.clip(color_distance / fade_span, 0.0, 1.0)
    whiteness_weight = 1.0 - distance_weight
    shrink_ratio = np.clip(alpha_ratio * (0.18 + 0.82 * distance_weight), 0.0, 1.0)
    proposed_alpha = np.round(shrink_ratio * 255.0).astype(np.uint8)
    zero_mask = target_mask & (whiteness_weight >= 0.72) & (tightened <= 176)
    tightened[target_mask] = proposed_alpha[target_mask]
    tightened[zero_mask] = 0
    return tightened
def _smooth_transition_alpha(
    alpha: np.ndarray,
    *,
    locked_mask: np.ndarray,
    iterations: int,
) -> np.ndarray:
    smoothed = np.array(alpha, copy=True).astype(np.uint16)
    editable_mask = (~locked_mask) & (smoothed > 0) & (smoothed < 255)
    if not np.any(editable_mask):
        return alpha
    for _ in range(max(0, int(iterations))):
        padded = np.pad(smoothed, 1, mode="edge")
        neighbor_sum = np.zeros_like(smoothed, dtype=np.uint16)
        for offset_y in range(3):
            for offset_x in range(3):
                neighbor_sum += padded[offset_y : offset_y + smoothed.shape[0], offset_x : offset_x + smoothed.shape[1]]
        averaged = np.round(neighbor_sum.astype(np.float32) / 9.0).astype(np.uint16)
        smoothed[editable_mask] = averaged[editable_mask]
    return np.clip(smoothed, 0, 255).astype(np.uint8)
def _resolve_bright_fringe_threshold(background: BackgroundModel) -> int:
    background_mean = int(np.mean(background.color))
    return max(196, min(228, background_mean - 44))
def _suppress_supported_bright_fringe(
    *,
    alpha: np.ndarray,
    rgb: np.ndarray,
    background: BackgroundModel,
) -> np.ndarray:
    """压掉附着在真实前景边缘上的高亮背景残留，减少断续白边。"""
    suppressed = np.array(alpha, copy=True)
    edge_mask = (suppressed > 0) & (suppressed < 255)
    if not np.any(edge_mask):
        return suppressed
    background_like = _background_like_mask(
        rgb,
        background=background,
        extra_color_tolerance=16,
        extra_cast_tolerance=2,
    )
    bright_threshold = _resolve_bright_fringe_threshold(background)
    bright_like = _bright_background_mask(rgb, bright_threshold)
    strong_support_mask = _dilate_mask(suppressed >= 200, steps=1)
    strong_neighbor_count = _count_alpha_neighbors(
        suppressed >= 160,
        include_diagonal=True,
    )
    bright_supported_region = (
        (suppressed > 0)
        & background_like
        & bright_like
        & strong_support_mask
    )
    wide_fill_protection_mask = _build_wide_fill_protection_mask(
        candidate_mask=bright_supported_region,
    )
    target_mask = (
        edge_mask
        & background_like
        & bright_like
        & strong_support_mask
        & (strong_neighbor_count >= 2)
    )
    target_mask = _limit_outline_cleanup_to_narrow_bands(
        target_mask=target_mask,
        occupied_mask=(suppressed > 0),
    )
    target_mask &= ~wide_fill_protection_mask
    if not np.any(target_mask):
        return suppressed
    brightness = np.mean(rgb.astype(np.float32), axis=2)
    background_mean = float(np.mean(background.color))
    brightness_weight = np.clip((brightness - max(220.0, background_mean - 22.0)) / 28.0, 0.0, 1.0)
    alpha_ratio = suppressed.astype(np.float32) / 255.0
    keep_ratio = np.clip(0.62 - 0.52 * brightness_weight - 0.16 * (1.0 - alpha_ratio), 0.08, 0.62)
    proposed_alpha = np.round(suppressed.astype(np.float32) * keep_ratio).astype(np.uint8)
    zero_mask = target_mask & (brightness_weight >= 0.42) & (suppressed <= 176)
    suppressed[target_mask] = np.minimum(suppressed[target_mask], proposed_alpha[target_mask])
    suppressed[zero_mask] = 0
    return suppressed
def _count_alpha_neighbors(mask: np.ndarray, *, include_diagonal: bool = True) -> np.ndarray:
    padded = np.pad(mask.astype(np.uint8), 1, mode="constant", constant_values=0)
    count = np.zeros(mask.shape, dtype=np.uint8)
    for offset_y in range(3):
        for offset_x in range(3):
            if offset_y == 1 and offset_x == 1:
                continue
            if not include_diagonal and abs(offset_y - 1) + abs(offset_x - 1) != 1:
                continue
            count += padded[offset_y : offset_y + mask.shape[0], offset_x : offset_x + mask.shape[1]]
    return count
def _clean_bright_outline_residue(
    *,
    rgb: np.ndarray,
    alpha: np.ndarray,
    background: BackgroundModel,
    protected_mask: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """清理贴着真实前景的亮色描边残留，包括接近实心的浅色污染像素。"""
    cleaned_rgb = np.array(rgb, copy=True)
    cleaned_alpha = np.array(alpha, copy=True)
    occupied_mask = cleaned_alpha > 0
    if not np.any(occupied_mask):
        return cleaned_rgb, cleaned_alpha
    rgb_int16 = cleaned_rgb.astype(np.int16)
    color_distance = _color_distance(rgb_int16, background.color)
    color_cast_distance = _color_cast_distance(rgb_int16, background.color)
    bright_threshold = _resolve_bright_fringe_threshold(background)
    highlight_like = _bright_background_mask(rgb_int16, bright_threshold) | _pale_highlight_mask(
        rgb_int16,
        background=background,
    )
    strong_foreground = cleaned_alpha >= 200
    support_core = strong_foreground & (~highlight_like) & (
        (color_distance >= background.tolerance + max(8, background.tolerance // 4))
        | (color_cast_distance >= background.color_cast_tolerance + 2)
    )
    if not np.any(support_core):
        return cleaned_rgb, cleaned_alpha
    strong_support_mask = _dilate_mask(support_core, steps=3)
    support_neighbor_count = _count_alpha_neighbors(
        support_core,
        include_diagonal=True,
    )
    target_mask = (
        occupied_mask
        & highlight_like
        & strong_support_mask
        & (support_neighbor_count >= 1)
    )
    if protected_mask is not None:
        target_mask &= ~np.asarray(protected_mask, dtype=bool)
    if not np.any(target_mask):
        return cleaned_rgb, cleaned_alpha
    target_mask = _limit_outline_cleanup_to_narrow_bands(
        target_mask=target_mask,
        occupied_mask=occupied_mask,
    )
    if not np.any(target_mask):
        return cleaned_rgb, cleaned_alpha
    alpha_neighbor_count = _count_alpha_neighbors(occupied_mask, include_diagonal=True)
    edge_like_mask = occupied_mask & (alpha_neighbor_count < 8)
    target_mask &= _dilate_mask(edge_like_mask, steps=1)
    if not np.any(target_mask):
        return cleaned_rgb, cleaned_alpha
    fade_mask = target_mask & (~support_core)
    if np.any(fade_mask):
        lowered_alpha = np.round(cleaned_alpha[fade_mask].astype(np.float32) * 0.42).astype(np.uint8)
        hard_clear_mask = cleaned_alpha[fade_mask] <= 176
        lowered_alpha[hard_clear_mask] = 0
        cleaned_alpha[fade_mask] = np.minimum(cleaned_alpha[fade_mask], lowered_alpha)
    replacement_rgb = _estimate_nearest_support_colors(
        cleaned_rgb.astype(np.uint8),
        target_mask=target_mask,
        support_mask=support_core,
        radius=5,
    )
    cleaned_rgb[target_mask] = replacement_rgb[target_mask]
    return cleaned_rgb, cleaned_alpha
def _has_alpha_opposite_pairs(mask: np.ndarray) -> np.ndarray:
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
def _estimate_nearest_support_colors(
    rgb: np.ndarray,
    *,
    target_mask: np.ndarray,
    support_mask: np.ndarray,
    radius: int,
) -> np.ndarray:
    result = rgb.astype(np.float32)
    target = np.asarray(target_mask, dtype=bool)
    support = np.asarray(support_mask, dtype=bool)
    if not np.any(target) or not np.any(support):
        return rgb.astype(np.uint8)
    height, width = target.shape
    resolved_radius = max(1, int(radius))
    padded_rgb = np.pad(
        rgb,
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
    return np.clip(result, 0.0, 255.0).astype(np.uint8)
def _limit_outline_cleanup_to_narrow_bands(
    *,
    target_mask: np.ndarray,
    occupied_mask: np.ndarray,
) -> np.ndarray:
    """只保留更像窄边缘污染的连通域，避免误伤大面积浅色填充块。"""
    candidate = np.asarray(target_mask, dtype=bool)
    if not np.any(candidate):
        return candidate
    result = np.zeros(candidate.shape, dtype=bool)
    occupied = np.asarray(occupied_mask, dtype=bool)
    for component in find_mask_components(candidate, connectivity=8):
        area = int(component["area"])
        left = int(component["left"])
        top = int(component["top"])
        right = int(component["right"])
        bottom = int(component["bottom"])
        width = max(1, right - left)
        height = max(1, bottom - top)
        bbox_area = max(1, width * height)
        fill_ratio = float(area) / float(bbox_area)
        min_side = min(width, height)
        max_side = max(width, height)
        local_mask = np.asarray(component["mask"], dtype=bool)
        occupied_crop = occupied[top:bottom, left:right]
        if occupied_crop.shape != local_mask.shape:
            continue
        if area <= 72:
            result[top:bottom, left:right][local_mask] = True
            continue
        if min_side <= 3 and fill_ratio <= 0.72:
            result[top:bottom, left:right][local_mask] = True
            continue
        if min_side <= 3 and max_side >= 18 and fill_ratio <= 0.35:
            result[top:bottom, left:right][local_mask] = True
            continue
    return result
def _build_wide_fill_protection_mask(
    *,
    candidate_mask: np.ndarray,
) -> np.ndarray:
    """保护更像真实浅色填充块的宽连通域，避免把它们当作亮边误压 alpha。"""
    candidate = np.asarray(candidate_mask, dtype=bool)
    if not np.any(candidate):
        return candidate
    result = np.zeros(candidate.shape, dtype=bool)
    for component in find_mask_components(candidate, connectivity=8):
        area = int(component["area"])
        left = int(component["left"])
        top = int(component["top"])
        right = int(component["right"])
        bottom = int(component["bottom"])
        width = max(1, right - left)
        height = max(1, bottom - top)
        bbox_area = max(1, width * height)
        fill_ratio = float(area) / float(bbox_area)
        min_side = min(width, height)
        max_side = max(width, height)
        local_mask = np.asarray(component["mask"], dtype=bool)
        if area >= 48 and min_side >= 6 and fill_ratio >= 0.32:
            result[top:bottom, left:right][local_mask] = True
            continue
        if area >= 64 and min_side >= 4 and max_side >= 12 and fill_ratio >= 0.48:
            result[top:bottom, left:right][local_mask] = True
            continue
    return result
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
def _decontaminate_edge_colors(
    rgb: np.ndarray,
    *,
    alpha: np.ndarray,
    background: BackgroundModel,
    protected_mask: np.ndarray | None = None,
) -> np.ndarray:
    result = rgb.astype(np.float32)
    alpha_ratio = alpha.astype(np.float32) / 255.0
    edge_mask = (alpha_ratio > 0.0) & (alpha_ratio < 1.0)
    if not np.any(edge_mask):
        return rgb.astype(np.uint8)
    safe_alpha = np.clip(alpha_ratio, 1.0 / 255.0, 1.0)
    background_rgb = background.color.reshape(1, 1, 3).astype(np.float32)
    recovered = (result - background_rgb * (1.0 - safe_alpha[..., None])) / safe_alpha[..., None]
    recovered = np.clip(recovered, 0.0, 255.0)
    local_foreground = _estimate_local_foreground_colors(rgb, alpha=alpha, radius=3).astype(np.float32)
    rgb_int16 = rgb.astype(np.int16)
    color_distance = _color_distance(rgb_int16, background.color.astype(np.int16)).astype(np.float32)
    distance_scale = max(8.0, float(np.max(color_distance)) if edge_mask.any() else 8.0)
    whiteness = np.clip(1.0 - (color_distance / distance_scale), 0.0, 1.0)
    local_weight = np.clip((1.0 - alpha_ratio) * (0.75 + 0.25 * whiteness), 0.0, 0.95)
    bright_fringe_mask = edge_mask & _background_like_mask(
        rgb_int16,
        background=background,
        extra_color_tolerance=32,
        extra_cast_tolerance=5,
    ) & (
        _bright_background_mask(
            rgb_int16,
            _resolve_bright_fringe_threshold(background),
        )
        | _pale_highlight_mask(
            rgb_int16,
            background=background,
        )
    ) & _dilate_mask(alpha >= 200, steps=2)
    if np.any(bright_fringe_mask):
        local_weight[bright_fringe_mask] = np.maximum(local_weight[bright_fringe_mask], 0.995)
    blend_base = recovered * (1.0 - local_weight[..., None]) + local_foreground * local_weight[..., None]
    original_residual = np.clip(alpha_ratio * 0.25, 0.0, 0.25)
    if np.any(bright_fringe_mask):
        original_residual[bright_fringe_mask] = 0.0
    blended = blend_base * (1.0 - original_residual[..., None]) + rgb.astype(np.float32) * original_residual[..., None]
    if np.any(bright_fringe_mask):
        blended[bright_fringe_mask] = (
            local_foreground[bright_fringe_mask] * 0.99
            + recovered[bright_fringe_mask] * 0.01
        )
    result[edge_mask] = blended[edge_mask]
    if protected_mask is not None:
        protected = np.asarray(protected_mask, dtype=bool)
        if np.any(protected):
            result[protected] = rgb.astype(np.float32)[protected]
    return np.clip(result, 0.0, 255.0).astype(np.uint8)
def _sharpen_supported_edge_detail(
    *,
    rgb: np.ndarray,
    alpha: np.ndarray,
    background: BackgroundModel,
    protected_mask: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """压实贴着主体的软边像素，减少发虚色块，让边缘更明确。"""
    sharpened_rgb = np.array(rgb, copy=True)
    sharpened_alpha = np.array(alpha, copy=True)
    edge_mask = (sharpened_alpha > 0) & (sharpened_alpha < 255)
    if not np.any(edge_mask):
        return sharpened_rgb, sharpened_alpha
    rgb_int16 = sharpened_rgb.astype(np.int16)
    highlight_like = _bright_background_mask(
        rgb_int16,
        _resolve_bright_fringe_threshold(background),
    ) | _pale_highlight_mask(
        rgb_int16,
        background=background,
    )
    saturation = np.max(rgb_int16, axis=2) - np.min(rgb_int16, axis=2)
    support_core = (sharpened_alpha >= 200) & (~highlight_like)
    if not np.any(support_core):
        return sharpened_rgb, sharpened_alpha
    support_near_mask = _dilate_mask(support_core, steps=2)
    target_mask = edge_mask & support_near_mask
    if not np.any(target_mask):
        return sharpened_rgb, sharpened_alpha
    support_rgb = _estimate_nearest_support_colors(
        sharpened_rgb.astype(np.uint8),
        target_mask=target_mask,
        support_mask=support_core,
        radius=4,
    ).astype(np.uint8)
    support_rgb_int16 = support_rgb.astype(np.int16)
    support_brightness = np.mean(support_rgb_int16.astype(np.float32), axis=2)
    brightness = np.mean(rgb_int16.astype(np.float32), axis=2)
    distance_to_support = np.max(np.abs(rgb_int16 - support_rgb_int16), axis=2)
    alpha_gap = np.abs(sharpened_alpha.astype(np.int16) - 255)
    hazy_mask = target_mask & (
        highlight_like
        | ((saturation <= 88) & (brightness >= support_brightness - 6.0) & (distance_to_support >= 18))
        | ((saturation <= 72) & (distance_to_support >= 28))
        | ((distance_to_support >= 22) & (alpha_gap >= 72))
    )
    if protected_mask is not None:
        hazy_mask &= ~np.asarray(protected_mask, dtype=bool)
    if not np.any(hazy_mask):
        return sharpened_rgb, sharpened_alpha
    sharpened_rgb[hazy_mask] = support_rgb[hazy_mask]
    alpha_floor = np.where(highlight_like, 176, 144).astype(np.uint8)
    sharpened_alpha[hazy_mask] = np.maximum(sharpened_alpha[hazy_mask], alpha_floor[hazy_mask])
    return sharpened_rgb, sharpened_alpha
def _estimate_local_foreground_colors(
    rgb: np.ndarray,
    *,
    alpha: np.ndarray,
    radius: int,
) -> np.ndarray:
    foreground = alpha >= 200
    if not np.any(foreground):
        return rgb.astype(np.uint8)
    result = rgb.astype(np.float32)
    edge_mask = (alpha > 0) & (alpha < 255)
    if not np.any(edge_mask):
        return rgb.astype(np.uint8)
    height, width = alpha.shape
    resolved_radius = max(1, int(radius))
    padded_rgb = np.pad(
        rgb,
        ((resolved_radius, resolved_radius), (resolved_radius, resolved_radius), (0, 0)),
        mode="edge",
    )
    padded_foreground = np.pad(foreground, resolved_radius, mode="constant", constant_values=False)
    best_distance = np.full(alpha.shape, resolved_radius * resolved_radius + 1, dtype=np.int16)
    for dy in range(-resolved_radius, resolved_radius + 1):
        for dx in range(-resolved_radius, resolved_radius + 1):
            distance = dy * dy + dx * dx
            if distance > resolved_radius * resolved_radius:
                continue
            top = resolved_radius + dy
            left = resolved_radius + dx
            candidate_mask = padded_foreground[top : top + height, left : left + width]
            update_mask = edge_mask & candidate_mask & (distance < best_distance)
            if not np.any(update_mask):
                continue
            candidate_rgb = padded_rgb[top : top + height, left : left + width]
            result[update_mask] = candidate_rgb[update_mask]
            best_distance[update_mask] = distance
    return np.clip(result, 0.0, 255.0).astype(np.uint8)
