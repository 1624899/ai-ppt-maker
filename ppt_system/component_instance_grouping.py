from __future__ import annotations

from typing import Any

import numpy as np

from ppt_system.component_geometry import bbox_gap_distance, component_bbox, merge_bbox
from ppt_system.component_postprocess import merge_component_group


def group_components_into_instances(
    components: list[dict[str, Any]],
    *,
    image_width: int,
    image_height: int,
    merge_distance: int,
) -> list[dict[str, Any]]:
    """按 barrier 区域、颜色和局部连续性把组件组装成更像实例的资产。"""
    if len(components) <= 1 or int(merge_distance) <= 0:
        return components

    pending = [dict(component) for component in components]
    union_find = _UnionFind(len(pending))
    max_gap = max(3, int(merge_distance) + 2)
    max_group_span = max(36, int(min(image_width, image_height) * 0.22))

    for first_index in range(len(pending)):
        first = pending[first_index]
        if bool(first.get("is_container", False)):
            continue
        for second_index in range(first_index + 1, len(pending)):
            second = pending[second_index]
            if bool(second.get("is_container", False)):
                continue
            if not _should_group_components(
                first,
                second,
                max_gap=max_gap,
                max_group_span=max_group_span,
            ):
                continue
            union_find.union(first_index, second_index)

    groups: dict[int, list[int]] = {}
    for index in range(len(pending)):
        groups.setdefault(union_find.find(index), []).append(index)

    merged: list[dict[str, Any]] = []
    for group_indices in groups.values():
        if len(group_indices) == 1:
            merged.append(pending[group_indices[0]])
            continue
        group = [pending[index] for index in group_indices]
        merged_component = merge_component_group(
            group,
            contains_anchor=False,
            extra_metadata={
                "is_instance_group": True,
                "instance_group_size": len(group),
                "primary_region_id": _resolve_primary_region_id(group),
                "adjacent_region_ids": _merge_region_ids(group),
                "enclosed_region_ids": _merge_enclosed_region_ids(group),
            },
        )
        if _should_keep_merged_group(merged_component, group=group):
            merged.append(merged_component)
            continue
        merged.extend(group)
    return merged


def _should_group_components(
    first: dict[str, Any],
    second: dict[str, Any],
    *,
    max_gap: int,
    max_group_span: int,
) -> bool:
    if not _share_mergeable_region(first, second):
        return False
    if bbox_gap_distance(component_bbox(first), component_bbox(second)) > max_gap:
        return False
    if _dominant_color_distance(first, second) > _color_tolerance(first, second):
        return False
    if _stroke_scale_ratio(first, second) > 2.6:
        return False

    merged_bbox = merge_bbox(component_bbox(first), component_bbox(second))
    merged_width = merged_bbox[2] - merged_bbox[0]
    merged_height = merged_bbox[3] - merged_bbox[1]
    if merged_width > max_group_span or merged_height > max_group_span:
        return False

    if _looks_like_distant_layout_pair(first, second, max_gap=max_gap):
        return False
    return True


def _share_mergeable_region(first: dict[str, Any], second: dict[str, Any]) -> bool:
    first_regions = set(_component_region_ids(first))
    second_regions = set(_component_region_ids(second))
    if not first_regions or not second_regions:
        return False
    shared = first_regions & second_regions
    if not shared:
        return False
    if 0 in shared and len(shared) == 1:
        return False
    return True


def _component_region_ids(component: dict[str, Any]) -> list[int]:
    enclosed = [int(region_id) for region_id in component.get("enclosed_region_ids", []) if int(region_id) > 0]
    if enclosed:
        return enclosed
    adjacent = [int(region_id) for region_id in component.get("adjacent_region_ids", []) if int(region_id) > 0]
    if adjacent:
        return adjacent
    primary = int(component.get("primary_region_id", 0))
    return [primary] if primary > 0 else []


def _dominant_color_distance(first: dict[str, Any], second: dict[str, Any]) -> float:
    first_color = np.asarray(
        first.get("dominant_color_vector", first.get("dominant_color", (255, 255, 255))),
        dtype=np.float32,
    )
    second_color = np.asarray(
        second.get("dominant_color_vector", second.get("dominant_color", (255, 255, 255))),
        dtype=np.float32,
    )
    return float(np.linalg.norm(first_color - second_color))


def _color_tolerance(first: dict[str, Any], second: dict[str, Any]) -> float:
    vivid_bonus = 0.0
    if float(first.get("average_saturation", 0.0)) >= 100.0 and float(second.get("average_saturation", 0.0)) >= 100.0:
        vivid_bonus = 12.0
    return 30.0 + vivid_bonus


def _stroke_scale_ratio(first: dict[str, Any], second: dict[str, Any]) -> float:
    first_scale = _component_stroke_scale(first)
    second_scale = _component_stroke_scale(second)
    return max(first_scale, second_scale) / max(1.0, min(first_scale, second_scale))


def _component_stroke_scale(component: dict[str, Any]) -> float:
    width = max(1, int(component["right"]) - int(component["left"]))
    height = max(1, int(component["bottom"]) - int(component["top"]))
    area = max(1, int(component["area"]))
    density = area / max(1, width * height)
    return max(1.0, min(width, height) * max(0.35, density))


def _looks_like_distant_layout_pair(
    first: dict[str, Any],
    second: dict[str, Any],
    *,
    max_gap: int,
) -> bool:
    first_bbox = component_bbox(first)
    second_bbox = component_bbox(second)
    merged_bbox = merge_bbox(first_bbox, second_bbox)
    merged_width = merged_bbox[2] - merged_bbox[0]
    merged_height = merged_bbox[3] - merged_bbox[1]
    total_area = int(first["area"]) + int(second["area"])
    density = total_area / max(1, merged_width * merged_height)
    gap = bbox_gap_distance(component_bbox(first), component_bbox(second))
    return bool(
        gap >= max_gap
        and density <= 0.14
        and (merged_width >= 48 or merged_height >= 48)
    )


def _should_keep_merged_group(
    merged_component: dict[str, Any],
    *,
    group: list[dict[str, Any]],
) -> bool:
    width = max(1, int(merged_component["right"]) - int(merged_component["left"]))
    height = max(1, int(merged_component["bottom"]) - int(merged_component["top"]))
    density = int(merged_component["area"]) / max(1, width * height)
    if density <= 0.08 and len(group) <= 2:
        return False
    return True


def _resolve_primary_region_id(group: list[dict[str, Any]]) -> int:
    counts: dict[int, int] = {}
    for component in group:
        primary = int(component.get("primary_region_id", 0))
        if primary <= 0:
            continue
        counts[primary] = counts.get(primary, 0) + 1
    if not counts:
        return 0
    return max(counts.items(), key=lambda item: item[1])[0]


def _merge_region_ids(group: list[dict[str, Any]]) -> list[int]:
    ids = sorted(
        {
            int(region_id)
            for component in group
            for region_id in component.get("adjacent_region_ids", [])
            if int(region_id) > 0
        }
    )
    return ids


def _merge_enclosed_region_ids(group: list[dict[str, Any]]) -> list[int]:
    ids = sorted(
        {
            int(region_id)
            for component in group
            for region_id in component.get("enclosed_region_ids", [])
            if int(region_id) > 0
        }
    )
    return ids

class _UnionFind:
    def __init__(self, size: int) -> None:
        self._parents = list(range(max(0, int(size))))

    def find(self, index: int) -> int:
        parent = self._parents[index]
        while parent != self._parents[parent]:
            self._parents[parent] = self._parents[self._parents[parent]]
            parent = self._parents[parent]
        self._parents[index] = parent
        return parent

    def union(self, first: int, second: int) -> None:
        first_root = self.find(first)
        second_root = self.find(second)
        if first_root == second_root:
            return
        self._parents[second_root] = first_root
