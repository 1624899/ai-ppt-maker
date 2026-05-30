from __future__ import annotations

from typing import Any

import numpy as np


def restore_removed_regions(
    crop_array: np.ndarray,
    *,
    fill_mask: np.ndarray,
) -> np.ndarray:
    """对母资产中被拆出的子图标区域做平滑回填，避免移动后露出残影。"""
    if crop_array.ndim != 3 or crop_array.shape[2] != 4:
        return crop_array

    local_fill_mask = np.asarray(fill_mask, dtype=bool)
    if local_fill_mask.shape != crop_array.shape[:2] or not local_fill_mask.any():
        return crop_array

    expanded_fill_mask = _dilate_mask(local_fill_mask, radius=2)
    result = np.array(crop_array, copy=True)
    alpha = result[..., 3].astype(np.float32)
    rgb = result[..., :3].astype(np.float32)

    known_mask = (~expanded_fill_mask) & (alpha > 0)
    pending_mask = expanded_fill_mask & (alpha > 0)
    if not pending_mask.any():
        return crop_array

    filled_rgb = np.array(rgb, copy=True)
    filled_alpha = np.array(alpha, copy=True)
    working_known = np.array(known_mask, copy=True)

    max_steps = int(pending_mask.sum()) + 8
    for _ in range(max_steps):
        if not pending_mask.any():
            break
        progress = False
        next_pending = np.array(pending_mask, copy=True)
        ys, xs = np.nonzero(pending_mask)
        for y, x in zip(ys.tolist(), xs.tolist()):
            neighbor_values_rgb: list[np.ndarray] = []
            neighbor_values_alpha: list[float] = []
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    ny = y + dy
                    nx = x + dx
                    if ny < 0 or nx < 0 or ny >= crop_array.shape[0] or nx >= crop_array.shape[1]:
                        continue
                    if not working_known[ny, nx]:
                        continue
                    neighbor_values_rgb.append(filled_rgb[ny, nx])
                    neighbor_values_alpha.append(float(filled_alpha[ny, nx]))
            if not neighbor_values_rgb:
                continue
            filled_rgb[y, x] = np.mean(np.stack(neighbor_values_rgb, axis=0), axis=0)
            filled_alpha[y, x] = float(np.mean(neighbor_values_alpha))
            working_known[y, x] = True
            next_pending[y, x] = False
            progress = True
        pending_mask = next_pending
        if not progress:
            break

    if pending_mask.any():
        fallback_rgb = _estimate_fallback_rgb(filled_rgb, working_known)
        fallback_alpha = _estimate_fallback_alpha(filled_alpha, working_known)
        filled_rgb[pending_mask] = fallback_rgb
        filled_alpha[pending_mask] = fallback_alpha

    result[..., :3] = np.clip(filled_rgb, 0, 255).astype(np.uint8)
    result[..., 3] = np.clip(filled_alpha, 0, 255).astype(np.uint8)
    return result


def _dilate_mask(mask: np.ndarray, *, radius: int) -> np.ndarray:
    if radius <= 0:
        return np.asarray(mask, dtype=bool)

    expanded = np.asarray(mask, dtype=bool)
    for _ in range(radius):
        current = np.array(expanded, copy=True)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                shifted = np.zeros_like(current, dtype=bool)
                src_y_start = max(0, -dy)
                src_y_end = current.shape[0] - max(0, dy)
                src_x_start = max(0, -dx)
                src_x_end = current.shape[1] - max(0, dx)
                dst_y_start = max(0, dy)
                dst_y_end = dst_y_start + (src_y_end - src_y_start)
                dst_x_start = max(0, dx)
                dst_x_end = dst_x_start + (src_x_end - src_x_start)
                shifted[dst_y_start:dst_y_end, dst_x_start:dst_x_end] = current[src_y_start:src_y_end, src_x_start:src_x_end]
                expanded |= shifted
    return expanded


def _estimate_fallback_rgb(rgb: np.ndarray, known_mask: np.ndarray) -> np.ndarray:
    if known_mask.any():
        return np.mean(rgb[known_mask], axis=0)
    return np.array([255.0, 255.0, 255.0], dtype=np.float32)


def _estimate_fallback_alpha(alpha: np.ndarray, known_mask: np.ndarray) -> float:
    if known_mask.any():
        return float(np.mean(alpha[known_mask]))
    return 255.0


def has_fill_mask(component: dict[str, Any]) -> bool:
    fill_mask = component.get("fill_mask")
    return isinstance(fill_mask, np.ndarray) and bool(np.asarray(fill_mask, dtype=bool).any())
