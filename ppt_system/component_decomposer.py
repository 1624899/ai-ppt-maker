from __future__ import annotations

from collections import deque
from typing import Any

import numpy as np


def decompose_components(
    components: list[dict[str, Any]],
    *,
    image_array: np.ndarray,
) -> list[dict[str, Any]]:
    """把大块组件进一步拆成框体资产与内部可匹配子资产。"""
    decomposed: list[dict[str, Any]] = []
    for component in components:
        decomposed.extend(_decompose_recursively(component, image_array=image_array))
    return decomposed


def _decompose_recursively(
    component: dict[str, Any],
    *,
    image_array: np.ndarray,
    depth: int = 0,
    max_depth: int = 2,
) -> list[dict[str, Any]]:
    if depth >= max_depth:
        return [component]

    pieces = _decompose_single_component(component, image_array=image_array)
    if len(pieces) <= 1:
        return [component]

    refined: list[dict[str, Any]] = []
    for piece in pieces:
        refined.extend(
            _decompose_recursively(
                piece,
                image_array=image_array,
                depth=depth + 1,
                max_depth=max_depth,
            )
        )
    return refined


def _decompose_single_component(
    component: dict[str, Any],
    *,
    image_array: np.ndarray,
) -> list[dict[str, Any]]:
    left = int(component["left"])
    top = int(component["top"])
    right = int(component["right"])
    bottom = int(component["bottom"])
    width = max(1, right - left)
    height = max(1, bottom - top)
    component_area = int(component["area"])
    bbox_area = max(1, width * height)
    density = component_area / bbox_area

    if width < 48 or height < 48 or density < 0.32:
        return [component]

    crop = np.asarray(image_array[top:bottom, left:right], dtype=np.uint8)
    component_mask = np.asarray(component["mask"], dtype=bool)
    opaque_mask = component_mask & (crop[..., 3] > 0)
    if int(opaque_mask.sum()) < 64:
        return [component]

    dominant_color = _estimate_dominant_color(crop, opaque_mask)
    detail_mask = _build_detail_mask(crop, opaque_mask, dominant_color)
    if int(detail_mask.sum()) < max(24, component_area // 80):
        return [component]

    detail_components = _find_mask_components(detail_mask)
    if not detail_components:
        return [component]

    edge_margin = max(6, min(width, height) // 18)
    isolated_masks: list[np.ndarray] = []
    isolated_fill_masks: list[np.ndarray] = []
    for detail_component in detail_components:
        if not _is_isolated_sub_asset(
            detail_component,
            width=width,
            height=height,
            edge_margin=edge_margin,
            host_area=component_area,
        ):
            continue
        isolated_mask = np.zeros_like(component_mask, dtype=bool)
        isolated_mask[
            int(detail_component["top"]) : int(detail_component["bottom"]),
            int(detail_component["left"]) : int(detail_component["right"]),
        ] = np.asarray(detail_component["mask"], dtype=bool)
        isolated_masks.append(isolated_mask)
        isolated_fill_masks.append(
            _build_expanded_bbox_mask(
                detail_component,
                canvas_shape=component_mask.shape,
                padding=max(3, min(width, height) // 24),
            )
        )

    if not isolated_masks:
        return [component]

    separated_mask = np.zeros_like(component_mask, dtype=bool)
    for isolated_mask in isolated_masks:
        separated_mask |= isolated_mask

    remaining_mask = component_mask & ~separated_mask
    remaining_area = int(remaining_mask.sum())
    isolated_area = int(separated_mask.sum())
    if remaining_area < max(32, component_area // 20) or isolated_area < max(24, component_area // 100):
        return [component]

    results: list[dict[str, Any]] = []
    remaining_component = _component_from_mask(remaining_mask, left=left, top=top)
    if remaining_component is not None:
        combined_fill_mask = np.zeros_like(remaining_mask, dtype=bool)
        for isolated_fill_mask in isolated_fill_masks:
            combined_fill_mask |= isolated_fill_mask
        if isinstance(component.get("fill_mask"), np.ndarray):
            inherited_fill_mask = np.asarray(component["fill_mask"], dtype=bool)
            if inherited_fill_mask.shape == combined_fill_mask.shape:
                combined_fill_mask |= inherited_fill_mask
        remaining_component["fill_mask"] = combined_fill_mask
        results.append(remaining_component)
    for isolated_mask in isolated_masks:
        isolated_component = _component_from_mask(isolated_mask, left=left, top=top)
        if isolated_component is not None:
            results.append(isolated_component)

    if len(results) <= 1:
        return [component]
    return results


def _estimate_dominant_color(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
    pixels = image[mask][:, :3]
    if pixels.size == 0:
        return np.array([255.0, 255.0, 255.0], dtype=np.float32)

    quantized = (pixels // 16).astype(np.int16)
    packed = (
        (quantized[:, 0] << 8)
        | (quantized[:, 1] << 4)
        | quantized[:, 2]
    )
    unique_values, inverse = np.unique(packed, return_inverse=True)
    counts = np.bincount(inverse)
    dominant_index = int(np.argmax(counts))
    dominant_pixels = pixels[inverse == dominant_index]
    return dominant_pixels.mean(axis=0).astype(np.float32)


def _build_detail_mask(
    image: np.ndarray,
    opaque_mask: np.ndarray,
    dominant_color: np.ndarray,
) -> np.ndarray:
    rgb = image[..., :3].astype(np.float32)
    alpha = image[..., 3].astype(np.float32)
    color_distance = np.linalg.norm(rgb - dominant_color[None, None, :], axis=2)
    channel_span = rgb.max(axis=2) - rgb.min(axis=2)
    alpha_fade = alpha < 235

    # 颜色偏离主体底色、具有明显色相，或者带有透明抗锯齿边缘时，都视为可拆分细节。
    detail_mask = opaque_mask & (
        (color_distance >= 26.0)
        | (channel_span >= 18.0)
        | (alpha_fade & (color_distance >= 12.0))
    )
    return detail_mask


def _is_isolated_sub_asset(
    component: dict[str, Any],
    *,
    width: int,
    height: int,
    edge_margin: int,
    host_area: int,
) -> bool:
    left = int(component["left"])
    top = int(component["top"])
    right = int(component["right"])
    bottom = int(component["bottom"])
    area = int(component["area"])
    component_width = max(1, right - left)
    component_height = max(1, bottom - top)
    bbox_area = max(1, component_width * component_height)
    density = area / bbox_area

    touches_outer_band = (
        left <= edge_margin
        or top <= edge_margin
        or right >= width - edge_margin
        or bottom >= height - edge_margin
    )
    inset_x = min(left, width - right)
    inset_y = min(top, height - bottom)
    sufficiently_inside = min(inset_x, inset_y) >= max(4, edge_margin // 2)
    not_too_large = bbox_area <= max(1600, int(width * height * 0.45))
    meaningful_area = area >= max(24, int(host_area * 0.0025))

    if touches_outer_band and not sufficiently_inside:
        return False
    if not meaningful_area or not not_too_large:
        return False
    if density >= 0.12:
        return True
    return area >= max(48, int(host_area * 0.004))


def _component_from_mask(
    mask: np.ndarray,
    *,
    left: int,
    top: int,
) -> dict[str, Any] | None:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    min_x = int(xs.min())
    max_x = int(xs.max())
    min_y = int(ys.min())
    max_y = int(ys.max())
    component_mask = mask[min_y : max_y + 1, min_x : max_x + 1].copy()
    return {
        "left": left + min_x,
        "top": top + min_y,
        "right": left + max_x + 1,
        "bottom": top + max_y + 1,
        "area": int(component_mask.sum()),
        "mask": component_mask,
    }


def _find_mask_components(mask: np.ndarray) -> list[dict[str, Any]]:
    height, width = mask.shape
    visited = np.zeros(mask.shape, dtype=bool)
    components: list[dict[str, Any]] = []
    neighbors = (
        (-1, -1),
        (0, -1),
        (1, -1),
        (-1, 0),
        (1, 0),
        (-1, 1),
        (0, 1),
        (1, 1),
    )

    ys, xs = np.nonzero(mask)
    for start_x, start_y in zip(xs, ys):
        if visited[start_y, start_x]:
            continue
        queue: deque[tuple[int, int]] = deque([(int(start_x), int(start_y))])
        visited[start_y, start_x] = True
        pixels: list[tuple[int, int]] = []
        min_x = max_x = int(start_x)
        min_y = max_y = int(start_y)

        while queue:
            current_x, current_y = queue.popleft()
            pixels.append((current_x, current_y))
            min_x = min(min_x, current_x)
            max_x = max(max_x, current_x)
            min_y = min(min_y, current_y)
            max_y = max(max_y, current_y)

            for delta_x, delta_y in neighbors:
                next_x = current_x + delta_x
                next_y = current_y + delta_y
                if (
                    0 <= next_x < width
                    and 0 <= next_y < height
                    and mask[next_y, next_x]
                    and not visited[next_y, next_x]
                ):
                    visited[next_y, next_x] = True
                    queue.append((next_x, next_y))

        component_mask = np.zeros((max_y - min_y + 1, max_x - min_x + 1), dtype=bool)
        for pixel_x, pixel_y in pixels:
            component_mask[pixel_y - min_y, pixel_x - min_x] = True
        components.append(
            {
                "left": min_x,
                "top": min_y,
                "right": max_x + 1,
                "bottom": max_y + 1,
                "area": len(pixels),
                "mask": component_mask,
            }
        )
    return components


def _expand_mask(mask: np.ndarray, *, radius: int) -> np.ndarray:
    expanded = np.array(np.asarray(mask, dtype=bool), copy=True)
    for _ in range(max(0, int(radius))):
        current = np.array(expanded, copy=True)
        for delta_y in (-1, 0, 1):
            for delta_x in (-1, 0, 1):
                if delta_x == 0 and delta_y == 0:
                    continue
                shifted = np.zeros_like(current, dtype=bool)
                src_y_start = max(0, -delta_y)
                src_y_end = current.shape[0] - max(0, delta_y)
                src_x_start = max(0, -delta_x)
                src_x_end = current.shape[1] - max(0, delta_x)
                dst_y_start = max(0, delta_y)
                dst_y_end = dst_y_start + (src_y_end - src_y_start)
                dst_x_start = max(0, delta_x)
                dst_x_end = dst_x_start + (src_x_end - src_x_start)
                shifted[dst_y_start:dst_y_end, dst_x_start:dst_x_end] = current[src_y_start:src_y_end, src_x_start:src_x_end]
                expanded |= shifted
    return expanded


def _build_expanded_bbox_mask(
    component: dict[str, Any],
    *,
    canvas_shape: tuple[int, int],
    padding: int,
) -> np.ndarray:
    mask = np.zeros(canvas_shape, dtype=bool)
    left = max(0, int(component["left"]) - padding)
    top = max(0, int(component["top"]) - padding)
    right = min(canvas_shape[1], int(component["right"]) + padding)
    bottom = min(canvas_shape[0], int(component["bottom"]) + padding)
    if left < right and top < bottom:
        mask[top:bottom, left:right] = True
    return mask
