from __future__ import annotations

from collections import deque
from typing import Any

import numpy as np

try:
    import cv2  # type: ignore
except ImportError:  # pragma: no cover - 运行时按环境决定
    cv2 = None


def find_mask_components(mask: np.ndarray, *, connectivity: int = 8) -> list[dict[str, Any]]:
    """提取二值 mask 的连通域，优先使用 OpenCV，缺失时回退到纯 NumPy 实现。"""
    binary = np.asarray(mask, dtype=np.uint8)
    if binary.ndim != 2 or not np.any(binary):
        return []

    resolved_connectivity = 4 if int(connectivity) == 4 else 8
    if cv2 is not None:
        return _find_mask_components_with_cv2(binary, connectivity=resolved_connectivity)
    return _find_mask_components_with_bfs(binary > 0, connectivity=resolved_connectivity)


def grow_mask_from_seed(
    *,
    candidate_mask: np.ndarray,
    seed_mask: np.ndarray,
    connectivity: int = 8,
) -> np.ndarray:
    """保留 candidate 中与 seed 同连通域的区域。"""
    candidate = np.asarray(candidate_mask, dtype=bool)
    seeds = np.asarray(seed_mask, dtype=bool) & candidate
    if candidate.ndim != 2 or not np.any(candidate) or not np.any(seeds):
        return np.zeros(candidate.shape, dtype=bool)

    resolved_connectivity = 4 if int(connectivity) == 4 else 8
    if cv2 is not None:
        return _grow_mask_from_seed_with_cv2(candidate, seeds, connectivity=resolved_connectivity)
    return _grow_mask_from_seed_with_bfs(candidate, seeds, connectivity=resolved_connectivity)


def flood_mask_from_border(candidate_mask: np.ndarray, *, connectivity: int = 4) -> np.ndarray:
    """提取与图像边缘连通的 candidate 区域。"""
    candidate = np.asarray(candidate_mask, dtype=bool)
    if candidate.ndim != 2 or not np.any(candidate):
        return np.zeros(candidate.shape, dtype=bool)

    seeds = np.zeros(candidate.shape, dtype=bool)
    seeds[0, :] = candidate[0, :]
    seeds[-1, :] = candidate[-1, :]
    seeds[:, 0] |= candidate[:, 0]
    seeds[:, -1] |= candidate[:, -1]
    return grow_mask_from_seed(
        candidate_mask=candidate,
        seed_mask=seeds,
        connectivity=connectivity,
    )


def _find_mask_components_with_cv2(binary: np.ndarray, *, connectivity: int) -> list[dict[str, Any]]:
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        binary,
        connectivity=connectivity,
    )

    components: list[dict[str, Any]] = []
    for label in range(1, int(count)):
        left = int(stats[label, cv2.CC_STAT_LEFT])
        top = int(stats[label, cv2.CC_STAT_TOP])
        width = int(stats[label, cv2.CC_STAT_WIDTH])
        height = int(stats[label, cv2.CC_STAT_HEIGHT])
        area = int(stats[label, cv2.CC_STAT_AREA])
        right = left + width
        bottom = top + height
        component_labels = labels[top:bottom, left:right]
        component_mask = component_labels == label
        components.append(
            {
                "left": left,
                "top": top,
                "right": right,
                "bottom": bottom,
                "area": area,
                "mask": component_mask,
            }
        )
    return components


def _grow_mask_from_seed_with_cv2(candidate: np.ndarray, seeds: np.ndarray, *, connectivity: int) -> np.ndarray:
    count, labels = cv2.connectedComponents(
        candidate.astype(np.uint8),
        connectivity=connectivity,
    )
    seed_labels = np.unique(labels[seeds])
    seed_labels = seed_labels[seed_labels > 0]
    if seed_labels.size == 0:
        return np.zeros(candidate.shape, dtype=bool)
    return np.isin(labels, seed_labels[: int(count)] if seed_labels.size else seed_labels)


def _find_mask_components_with_bfs(mask: np.ndarray, *, connectivity: int) -> list[dict[str, Any]]:
    visited = np.zeros(mask.shape, dtype=bool)
    offsets = _neighbor_offsets(connectivity)
    height, width = mask.shape
    components: list[dict[str, Any]] = []

    ys, xs = np.nonzero(mask)
    for start_y, start_x in zip(ys.tolist(), xs.tolist()):
        if visited[start_y, start_x]:
            continue
        pixels = _collect_component_pixels(
            mask=mask,
            visited=visited,
            start_y=start_y,
            start_x=start_x,
            offsets=offsets,
            height=height,
            width=width,
        )
        component = _build_component_from_pixels(pixels)
        if component is not None:
            components.append(component)
    return components


def _grow_mask_from_seed_with_bfs(candidate: np.ndarray, seeds: np.ndarray, *, connectivity: int) -> np.ndarray:
    offsets = _neighbor_offsets(connectivity)
    height, width = candidate.shape
    grown = np.zeros(candidate.shape, dtype=bool)
    queue: deque[tuple[int, int]] = deque()

    ys, xs = np.nonzero(seeds)
    for y, x in zip(ys.tolist(), xs.tolist()):
        grown[y, x] = True
        queue.append((y, x))

    while queue:
        current_y, current_x = queue.popleft()
        for delta_y, delta_x in offsets:
            next_y = current_y + delta_y
            next_x = current_x + delta_x
            if not (0 <= next_y < height and 0 <= next_x < width):
                continue
            if not candidate[next_y, next_x] or grown[next_y, next_x]:
                continue
            grown[next_y, next_x] = True
            queue.append((next_y, next_x))
    return grown


def _collect_component_pixels(
    *,
    mask: np.ndarray,
    visited: np.ndarray,
    start_y: int,
    start_x: int,
    offsets: tuple[tuple[int, int], ...],
    height: int,
    width: int,
) -> list[tuple[int, int]]:
    queue: deque[tuple[int, int]] = deque([(start_y, start_x)])
    visited[start_y, start_x] = True
    pixels: list[tuple[int, int]] = []

    while queue:
        current_y, current_x = queue.popleft()
        pixels.append((current_y, current_x))
        for delta_y, delta_x in offsets:
            next_y = current_y + delta_y
            next_x = current_x + delta_x
            if not (0 <= next_y < height and 0 <= next_x < width):
                continue
            if visited[next_y, next_x] or not mask[next_y, next_x]:
                continue
            visited[next_y, next_x] = True
            queue.append((next_y, next_x))
    return pixels


def _build_component_from_pixels(pixels: list[tuple[int, int]]) -> dict[str, Any] | None:
    if not pixels:
        return None
    ys = [pixel[0] for pixel in pixels]
    xs = [pixel[1] for pixel in pixels]
    top = min(ys)
    bottom = max(ys) + 1
    left = min(xs)
    right = max(xs) + 1
    local_mask = np.zeros((bottom - top, right - left), dtype=bool)
    for y, x in pixels:
        local_mask[y - top, x - left] = True
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "area": len(pixels),
        "mask": local_mask,
    }


def _neighbor_offsets(connectivity: int) -> tuple[tuple[int, int], ...]:
    if int(connectivity) == 4:
        return ((-1, 0), (1, 0), (0, -1), (0, 1))
    return (
        (-1, -1),
        (-1, 0),
        (-1, 1),
        (0, -1),
        (0, 1),
        (1, -1),
        (1, 0),
        (1, 1),
    )
