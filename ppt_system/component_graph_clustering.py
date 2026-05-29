from __future__ import annotations

from typing import Any

import numpy as np

from ppt_system.component_geometry import bbox_gap_distance, component_bbox, component_long_side, merge_bbox
from ppt_system.component_postprocess import merge_component_group
from ppt_system.cv_mask_components import find_mask_components


DEFAULT_COLOR_DIST_DASH = 35.0
DEFAULT_DIRECTION_SIM_DASH = 0.88


def merge_structural_components(
    components: list[dict[str, Any]],
    *,
    image_array: np.ndarray,
    merge_distance: int,
    color_dist_dash: float = DEFAULT_COLOR_DIST_DASH,
    direction_sim_dash: float = DEFAULT_DIRECTION_SIM_DASH,
) -> list[dict[str, Any]]:
    """基于组件特征做图聚类，优先合并结构明确的虚线/断线。"""
    if len(components) <= 1 or int(merge_distance) <= 0:
        return components

    featured = [
        enrich_component_structure(component, image_array=image_array)
        for component in components
    ]
    union_find = _UnionFind(len(featured))
    max_dash_gap = max(12, int(merge_distance) * 4)

    for first_index in range(len(featured)):
        for second_index in range(first_index + 1, len(featured)):
            first = featured[first_index]
            second = featured[second_index]
            if _should_merge_dash_like_components(
                first,
                second,
                max_dash_gap=max_dash_gap,
                color_tolerance=float(color_dist_dash),
                direction_similarity_threshold=float(direction_sim_dash),
            ):
                union_find.union(first_index, second_index)

    groups: dict[int, list[int]] = {}
    for index in range(len(featured)):
        groups.setdefault(union_find.find(index), []).append(index)

    merged: list[dict[str, Any]] = []
    for group_indices in groups.values():
        group = [featured[index] for index in group_indices]
        if len(group) == 1:
            merged.append(group[0])
            continue
        merged.append(
            merge_component_group(
                group,
                contains_anchor=False,
                extra_metadata={
                    "is_dashed_line_group": True,
                    "dash_group_size": len(group),
                    "dash_orientation": _infer_group_orientation(group),
                    "structural_merge": True,
                },
            )
        )
    return merged


def enrich_component_structure(
    component: dict[str, Any],
    *,
    image_array: np.ndarray,
) -> dict[str, Any]:
    enriched = dict(component)
    left = int(component["left"])
    top = int(component["top"])
    right = int(component["right"])
    bottom = int(component["bottom"])
    width = max(1, right - left)
    height = max(1, bottom - top)
    area = int(component["area"])
    mask = np.asarray(component["mask"], dtype=bool)
    ys, xs = np.nonzero(mask)

    if len(xs) == 0:
        centroid = np.array([left + width / 2.0, top + height / 2.0], dtype=np.float32)
        direction = np.array([1.0, 0.0], dtype=np.float32)
    else:
        global_xs = xs.astype(np.float32) + float(left)
        global_ys = ys.astype(np.float32) + float(top)
        centroid = np.array([float(global_xs.mean()), float(global_ys.mean())], dtype=np.float32)
        direction = _estimate_pca_direction(global_xs, global_ys)

    crop = image_array[top:bottom, left:right]
    alpha = crop[..., 3]
    rgb = crop[..., :3]
    strong_mask = mask & (alpha >= 96)
    color_mask = strong_mask if bool(np.any(strong_mask)) else (mask & (alpha > 0))
    if bool(np.any(color_mask)):
        color = np.median(rgb[color_mask], axis=0).astype(np.float32)
    else:
        color = np.array([255.0, 255.0, 255.0], dtype=np.float32)

    enriched.update(
        {
            "centroid": centroid,
            "direction": direction,
            "dominant_color_vector": color,
            "fill_ratio": float(area / max(1, width * height)),
            "aspect_ratio": float(max(width, height) / max(1, min(width, height))),
        }
    )
    return enriched


def split_suspicious_sparse_components(
    components: list[dict[str, Any]],
    *,
    image_array: np.ndarray,
    strong_alpha_threshold: int = 96,
    min_bbox_area: int = 5000,
    max_fill_ratio: float = 0.08,
) -> list[dict[str, Any]]:
    """把低填充率的大粘连块按 strong alpha 岛拆开，避免弱桥接导致欠切。"""
    result: list[dict[str, Any]] = []
    for component in components:
        split_children = _split_component_by_strong_islands(
            component,
            image_array=image_array,
            strong_alpha_threshold=int(strong_alpha_threshold),
            min_bbox_area=int(min_bbox_area),
            max_fill_ratio=float(max_fill_ratio),
        )
        result.extend(split_children)
    return result


def _split_component_by_strong_islands(
    component: dict[str, Any],
    *,
    image_array: np.ndarray,
    strong_alpha_threshold: int,
    min_bbox_area: int,
    max_fill_ratio: float,
) -> list[dict[str, Any]]:
    left = int(component["left"])
    top = int(component["top"])
    right = int(component["right"])
    bottom = int(component["bottom"])
    width = max(1, right - left)
    height = max(1, bottom - top)
    bbox_area = width * height
    area = int(component["area"])
    fill_ratio = area / max(1, bbox_area)
    if bbox_area < min_bbox_area or fill_ratio >= max_fill_ratio:
        return [component]
    if bool(component.get("is_dashed_line_group", False)) or bool(component.get("is_color_coherent_group", False)):
        return [component]

    component_mask = np.asarray(component["mask"], dtype=bool)
    alpha = image_array[top:bottom, left:right, 3]
    strong_mask = component_mask & (alpha >= strong_alpha_threshold)
    islands = find_mask_components(strong_mask, connectivity=4)
    islands = [item for item in islands if int(item["area"]) >= max(3, min(24, area // 20))]
    if len(islands) <= 1:
        return [component]

    children: list[dict[str, Any]] = []
    for index, island in enumerate(islands, start=1):
        child_left = left + int(island["left"])
        child_top = top + int(island["top"])
        child_right = left + int(island["right"])
        child_bottom = top + int(island["bottom"])
        child = {
            "left": child_left,
            "top": child_top,
            "right": child_right,
            "bottom": child_bottom,
            "area": int(island["area"]),
            "mask": np.asarray(island["mask"], dtype=bool),
            "split_parent_bbox": (left, top, right, bottom),
            "split_child_index": index,
        }
        children.append(child)

    if _children_cover_meaningful_area(children, component):
        return children
    return [component]


def _children_cover_meaningful_area(
    children: list[dict[str, Any]],
    parent: dict[str, Any],
) -> bool:
    child_area = sum(int(child["area"]) for child in children)
    parent_area = max(1, int(parent["area"]))
    if child_area / parent_area < 0.35:
        return False
    parent_bbox = component_bbox(parent)
    child_bbox = component_bbox(children[0])
    for child in children[1:]:
        child_bbox = merge_bbox(child_bbox, component_bbox(child))
    parent_width = max(1, parent_bbox[2] - parent_bbox[0])
    parent_height = max(1, parent_bbox[3] - parent_bbox[1])
    child_width = max(1, child_bbox[2] - child_bbox[0])
    child_height = max(1, child_bbox[3] - child_bbox[1])
    return child_width / parent_width >= 0.35 or child_height / parent_height >= 0.35


def _should_merge_dash_like_components(
    first: dict[str, Any],
    second: dict[str, Any],
    *,
    max_dash_gap: int,
    color_tolerance: float,
    direction_similarity_threshold: float,
) -> bool:
    if not (_is_dash_like(first) and _is_dash_like(second)):
        return False
    if _color_distance(first, second) > color_tolerance:
        return False
    if _direction_similarity(first, second) < direction_similarity_threshold:
        return False

    direction = _average_direction(
        np.asarray(first["direction"], dtype=np.float32),
        np.asarray(second["direction"], dtype=np.float32),
    )
    delta = np.asarray(second["centroid"], dtype=np.float32) - np.asarray(first["centroid"], dtype=np.float32)
    along_distance = abs(float(np.dot(delta, direction)))
    perpendicular_distance = abs(float(direction[0] * delta[1] - direction[1] * delta[0]))
    gap = bbox_gap_distance(component_bbox(first), component_bbox(second))
    short_side = max(
        1,
        min(
            int(first["right"]) - int(first["left"]),
            int(first["bottom"]) - int(first["top"]),
            int(second["right"]) - int(second["left"]),
            int(second["bottom"]) - int(second["top"]),
        ),
    )
    if gap > max_dash_gap:
        return False
    if perpendicular_distance > max(4.0, short_side * 1.8, max_dash_gap * 0.35):
        return False
    return along_distance <= max_dash_gap + component_long_side(first) + component_long_side(second)


def _is_dash_like(component: dict[str, Any]) -> bool:
    width = max(1, int(component["right"]) - int(component["left"]))
    height = max(1, int(component["bottom"]) - int(component["top"]))
    long_side = max(width, height)
    short_side = min(width, height)
    fill_ratio = float(component.get("fill_ratio", int(component["area"]) / max(1, width * height)))
    return long_side >= 4 and short_side <= 10 and long_side / max(1, short_side) >= 1.8 and fill_ratio >= 0.35


def _estimate_pca_direction(xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    if len(xs) < 3:
        return np.array([1.0, 0.0], dtype=np.float32)
    points = np.column_stack([xs, ys]).astype(np.float32)
    centered = points - points.mean(axis=0, keepdims=True)
    covariance = np.cov(centered, rowvar=False)
    if covariance.shape != (2, 2) or not np.all(np.isfinite(covariance)):
        return np.array([1.0, 0.0], dtype=np.float32)
    values, vectors = np.linalg.eigh(covariance)
    direction = vectors[:, int(np.argmax(values))].astype(np.float32)
    norm = float(np.linalg.norm(direction))
    if norm <= 1e-6:
        return np.array([1.0, 0.0], dtype=np.float32)
    direction = direction / norm
    if direction[0] < 0:
        direction = -direction
    return direction

def _average_direction(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    if float(np.dot(first, second)) < 0:
        second = -second
    direction = first + second
    norm = float(np.linalg.norm(direction))
    if norm <= 1e-6:
        return first
    return direction / norm


def _direction_similarity(first: dict[str, Any], second: dict[str, Any]) -> float:
    first_direction = np.asarray(first["direction"], dtype=np.float32)
    second_direction = np.asarray(second["direction"], dtype=np.float32)
    return abs(float(np.dot(first_direction, second_direction)))


def _color_distance(first: dict[str, Any], second: dict[str, Any]) -> float:
    first_color = np.asarray(first["dominant_color_vector"], dtype=np.float32)
    second_color = np.asarray(second["dominant_color_vector"], dtype=np.float32)
    return float(np.linalg.norm(first_color - second_color))


def _infer_group_orientation(group: list[dict[str, Any]]) -> str:
    bbox = component_bbox(group[0])
    for component in group[1:]:
        bbox = merge_bbox(bbox, component_bbox(component))
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    if width >= height * 2:
        return "horizontal"
    if height >= width * 2:
        return "vertical"
    return "mixed"


class _UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, index: int) -> int:
        while self.parent[index] != index:
            self.parent[index] = self.parent[self.parent[index]]
            index = self.parent[index]
        return index

    def union(self, first: int, second: int) -> None:
        first_root = self.find(first)
        second_root = self.find(second)
        if first_root != second_root:
            self.parent[second_root] = first_root
