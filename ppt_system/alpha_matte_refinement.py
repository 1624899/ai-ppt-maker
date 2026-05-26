from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class BackgroundModel:
    color: np.ndarray
    tolerance: int


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

    # 极小图边框样本极易被前景污染，这时直接按白底模型处理更稳定。
    if min(height, width) <= 3 and np.any(bright_background):
        return BackgroundModel(color=np.array([255, 255, 255], dtype=np.int16), tolerance=8)

    border_width = max(1, min(height, width) // 40)
    border_mask = np.zeros((height, width), dtype=bool)
    border_mask[:border_width, :] = True
    border_mask[-border_width:, :] = True
    border_mask[:, :border_width] = True
    border_mask[:, -border_width:] = True

    border_pixels = rgb[border_mask]
    if border_pixels.size == 0:
        return BackgroundModel(color=np.array([255, 255, 255], dtype=np.int16), tolerance=24)

    background_color = np.median(border_pixels, axis=0)
    border_distance = np.max(np.abs(border_pixels - background_color), axis=1)
    tolerance = int(np.percentile(border_distance, 90)) + 12
    tolerance = max(12, min(tolerance, 72))
    if np.mean(background_color) < fallback_bg_threshold - 10 and np.any(bright_background):
        return BackgroundModel(
            color=np.array([255, 255, 255], dtype=np.int16),
            tolerance=max(8, tolerance // 2),
        )
    return BackgroundModel(color=background_color, tolerance=tolerance)


def build_color_guided_alpha(
    source_rgba: np.ndarray,
    *,
    background: BackgroundModel,
) -> np.ndarray:
    rgb = source_rgba[:, :, :3].astype(np.int16)
    color_distance = _color_distance(rgb, background.color)
    soft_band = max(12, min(56, int(background.tolerance * 1.6)))
    fade_start = max(0.0, float(background.tolerance) - min(8.0, float(background.tolerance) * 0.35))
    alpha_scale = np.clip((color_distance.astype(np.float32) - fade_start) / float(soft_band), 0.0, 1.0)
    guided_alpha = np.round(alpha_scale * 255.0).astype(np.uint8)
    hard_background = _bright_background_mask(rgb, 245)
    guided_alpha[hard_background] = 0
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

    base_alpha = np.where(initial_alpha > 0, initial_alpha, guided_alpha).astype(np.uint8)
    strong_foreground = (
        (base_alpha >= 200)
        | (color_distance >= background.tolerance + max(18, background.tolerance // 3))
    )
    candidate_foreground = (
        (base_alpha >= 10)
        | (color_distance >= max(8, background.tolerance - 8))
    )

    connected_foreground = _grow_from_seeds(
        candidate_mask=candidate_foreground,
        seed_mask=strong_foreground,
    )
    support_mask = _dilate_mask(connected_foreground, steps=1)
    supported_alpha = np.where(support_mask, base_alpha, 0).astype(np.uint8)

    promoted_alpha = _promote_supported_soft_edges(
        alpha=supported_alpha,
        connected_mask=connected_foreground,
        color_distance=color_distance,
        tolerance=background.tolerance,
    )
    fill_preserved_alpha = _preserve_enclosed_light_fill(
        alpha=promoted_alpha,
        color_distance=color_distance,
        connected_mask=connected_foreground,
        tolerance=background.tolerance,
    )
    bridged_alpha = _bridge_narrow_gaps(
        alpha=fill_preserved_alpha,
        color_distance=color_distance,
        tolerance=background.tolerance,
    )
    suppressed_alpha = _suppress_weak_white_fringe(
        alpha=bridged_alpha,
        color_distance=color_distance,
        tolerance=background.tolerance,
    )
    smoothed_alpha = _smooth_transition_alpha(
        suppressed_alpha,
        locked_mask=(suppressed_alpha >= 240) | (~support_mask),
        iterations=2,
    )
    decontaminated_rgb = _decontaminate_edge_colors(
        source_rgba[:, :, :3],
        alpha=smoothed_alpha,
        background_color=background.color,
    )

    result[:, :, :3] = decontaminated_rgb
    result[:, :, 3] = smoothed_alpha
    return result


def _bright_background_mask(rgb: np.ndarray, fallback_bg_threshold: int) -> np.ndarray:
    return (
        (rgb[:, :, 0] >= fallback_bg_threshold)
        & (rgb[:, :, 1] >= fallback_bg_threshold)
        & (rgb[:, :, 2] >= fallback_bg_threshold)
    )


def _color_distance(rgb: np.ndarray, background_color: np.ndarray) -> np.ndarray:
    return np.max(np.abs(rgb - background_color.reshape(1, 1, 3)), axis=2)


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


def _preserve_enclosed_light_fill(
    *,
    alpha: np.ndarray,
    color_distance: np.ndarray,
    connected_mask: np.ndarray,
    tolerance: int,
) -> np.ndarray:
    preserved = np.array(alpha, copy=True)
    near_background_mask = color_distance <= tolerance + 10
    border_background_mask = _flood_fill_from_border(near_background_mask)
    enclosed_light_fill_mask = (
        (~border_background_mask)
        & (color_distance >= max(4, tolerance // 3))
        & (color_distance <= tolerance + 10)
        & _dilate_mask(connected_mask, steps=2)
    )
    if not np.any(enclosed_light_fill_mask):
        return preserved

    # 被深色描边包围的浅色填充不应按背景抠除，给这类区域一个温和的 alpha 下限。
    fill_floor = np.clip(
        (color_distance.astype(np.int16) - max(2, tolerance // 4)) * 8,
        0,
        144,
    ).astype(np.uint8)
    preserved[enclosed_light_fill_mask] = np.maximum(
        preserved[enclosed_light_fill_mask],
        fill_floor[enclosed_light_fill_mask],
    )
    return preserved


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

    # 对细线中常见的 1px 断缝做桥接，避免后续切分把一根线拆成多段。
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
    color_distance: np.ndarray,
    tolerance: int,
) -> np.ndarray:
    suppressed = np.array(alpha, copy=True)
    weak_white_mask = (
        (suppressed > 0)
        & (suppressed <= 72)
        & (color_distance <= tolerance + 10)
    )
    if not np.any(weak_white_mask):
        return suppressed

    support_count = _count_alpha_neighbors(suppressed > 0)
    orthogonal_strong_neighbor_count = _count_alpha_neighbors(
        suppressed >= 160,
        include_diagonal=False,
    )
    removable = weak_white_mask & (support_count <= 2) & (orthogonal_strong_neighbor_count == 0)
    suppressed[removable] = 0
    return suppressed


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
    background_color: np.ndarray,
) -> np.ndarray:
    result = rgb.astype(np.float32)
    alpha_ratio = alpha.astype(np.float32) / 255.0
    edge_mask = (alpha_ratio > 0.0) & (alpha_ratio < 1.0)
    if not np.any(edge_mask):
        return rgb.astype(np.uint8)

    safe_alpha = np.clip(alpha_ratio, 1.0 / 255.0, 1.0)
    background = background_color.reshape(1, 1, 3).astype(np.float32)
    recovered = (result - background * (1.0 - safe_alpha[..., None])) / safe_alpha[..., None]
    result[edge_mask] = np.clip(recovered[edge_mask], 0.0, 255.0)
    return result.astype(np.uint8)
