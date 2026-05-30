from __future__ import annotations

from typing import Any

import numpy as np

from ppt_system.component_color_signature import enrich_component_with_color_signature
from ppt_system.component_geometry import bbox_gap, component_bbox, merge_bbox
from ppt_system.component_postprocess import merge_component_group


def merge_local_icon_fragments(
    components: list[dict[str, Any]],
    *,
    image_array: np.ndarray,
    image_width: int,
    image_height: int,
    merge_distance: int,
) -> list[dict[str, Any]]:
    """把小而相邻、整体像局部 icon 的碎片合并为一个资产。"""
    if len(components) <= 1 or int(merge_distance) <= 0:
        return components

    max_gap = max(3, min(18, int(merge_distance) * 2))
    max_icon_span = _resolve_max_icon_span(
        image_width=image_width,
        image_height=image_height,
    )
    enriched = [
        enrich_component_with_color_signature(component, image_array=image_array)
        for component in components
    ]
    candidate_indices = [
        index
        for index, component in enumerate(enriched)
        if _is_icon_fragment_candidate(component, max_icon_span=max_icon_span)
    ]
    if len(candidate_indices) <= 1:
        return components

    union_find = _UnionFind(len(enriched))
    for first_position, first_index in enumerate(candidate_indices):
        first = enriched[first_index]
        for second_index in candidate_indices[first_position + 1 :]:
            second = enriched[second_index]
            if _should_join_icon_fragments(
                first,
                second,
                max_gap=max_gap,
                max_icon_span=max_icon_span,
            ):
                union_find.union(first_index, second_index)

    groups: dict[int, list[int]] = {}
    for index in range(len(enriched)):
        groups.setdefault(union_find.find(index), []).append(index)

    result: list[dict[str, Any]] = []
    for group_indices in groups.values():
        if len(group_indices) == 1:
            result.append(enriched[group_indices[0]])
            continue
        group = [enriched[index] for index in group_indices]
        merged = merge_component_group(
            group,
            contains_anchor=False,
            extra_metadata={
                "is_icon_group": True,
                "icon_group_size": len(group),
            },
        )
        if _should_keep_icon_group(
            merged,
            group=group,
            max_icon_span=max_icon_span,
        ):
            result.append(merged)
            continue
        result.extend(group)
    return result


def _resolve_max_icon_span(*, image_width: int, image_height: int) -> int:
    short_side = max(1, min(int(image_width), int(image_height)))
    return max(28, min(160, int(round(short_side * 0.14))))


def _is_icon_fragment_candidate(
    component: dict[str, Any],
    *,
    max_icon_span: int,
) -> bool:
    width = _component_width(component)
    height = _component_height(component)
    long_side = max(width, height)
    short_side = min(width, height)
    area = int(component["area"])
    bbox_area = max(1, width * height)
    density = area / bbox_area
    aspect_ratio = long_side / max(1, short_side)

    if long_side > max_icon_span:
        return False
    if bool(component.get("is_container", False)) and not _is_compact_icon_shell(
        component,
        width=width,
        height=height,
        max_icon_span=max_icon_span,
    ):
        return False
    if area > max(900, int(max_icon_span * max_icon_span * 0.45)):
        return False
    if aspect_ratio >= 8.0 and long_side >= max(32, int(max_icon_span * 0.55)):
        return False
    return density >= 0.04


def _is_compact_icon_shell(
    component: dict[str, Any],
    *,
    width: int,
    height: int,
    max_icon_span: int,
) -> bool:
    """允许小型轮廓外壳参与 icon 聚合，但继续排除大布局框。"""
    long_side = max(width, height)
    short_side = min(width, height)
    if long_side > max_icon_span or short_side < 8:
        return False
    aspect_ratio = long_side / max(1, short_side)
    if aspect_ratio > 2.4:
        return False

    fill_ratio = float(component.get("fill_ratio", int(component["area"]) / max(1, width * height)))
    hole_ratio = float(component.get("hole_ratio", 0.0))
    perimeter_occupancy = float(component.get("perimeter_occupancy_ratio", 0.0))
    border_contact_count = int(component.get("border_contact_count", 0))
    return bool(
        fill_ratio <= 0.5
        and (
            hole_ratio >= 0.03
            or perimeter_occupancy >= 0.5
            or border_contact_count >= 2
        )
    )


def _should_join_icon_fragments(
    first: dict[str, Any],
    second: dict[str, Any],
    *,
    max_gap: int,
    max_icon_span: int,
) -> bool:
    if not _share_allowed_region(first, second):
        return False

    gap_x, gap_y = bbox_gap(first, second)
    if gap_x > max_gap or gap_y > max_gap:
        return False
    if gap_x > 0 and gap_y > 0 and gap_x + gap_y > max_gap + 2:
        return False

    merged_bbox = merge_bbox(component_bbox(first), component_bbox(second))
    merged_width = merged_bbox[2] - merged_bbox[0]
    merged_height = merged_bbox[3] - merged_bbox[1]
    if max(merged_width, merged_height) > max_icon_span:
        return False

    if _looks_like_parallel_line_pair(first, second):
        return False

    if _colors_are_compatible(first, second):
        return True

    return _is_compact_mixed_color_icon_pair(
        first,
        second,
        gap_x=gap_x,
        gap_y=gap_y,
        max_gap=max_gap,
        merged_width=merged_width,
        merged_height=merged_height,
    )


def _should_keep_icon_group(
    merged: dict[str, Any],
    *,
    group: list[dict[str, Any]],
    max_icon_span: int,
) -> bool:
    width = _component_width(merged)
    height = _component_height(merged)
    if max(width, height) > max_icon_span:
        return False

    density = int(merged["area"]) / max(1, width * height)
    if density < 0.06:
        return False
    if _looks_like_simple_line_collection(group, merged):
        return False
    if len(group) == 2 and not _colors_are_compatible(group[0], group[1]):
        return _is_compact_mixed_color_icon_pair(
            group[0],
            group[1],
            gap_x=bbox_gap(group[0], group[1])[0],
            gap_y=bbox_gap(group[0], group[1])[1],
            max_gap=max(3, int(max_icon_span * 0.12)),
            merged_width=width,
            merged_height=height,
        )
    return True


def _share_allowed_region(first: dict[str, Any], second: dict[str, Any]) -> bool:
    first_regions = _positive_region_ids(first)
    second_regions = _positive_region_ids(second)
    if first_regions and second_regions and not (first_regions & second_regions):
        return False
    return True


def _positive_region_ids(component: dict[str, Any]) -> set[int]:
    ids: set[int] = set()
    for key in ("enclosed_region_ids", "adjacent_region_ids"):
        for region_id in component.get(key, []):
            value = int(region_id)
            if value > 0:
                ids.add(value)
    primary_region_id = int(component.get("primary_region_id", 0))
    if primary_region_id > 0:
        ids.add(primary_region_id)
    return ids


def _colors_are_compatible(first: dict[str, Any], second: dict[str, Any]) -> bool:
    first_color = np.asarray(first.get("dominant_color", (255, 255, 255)), dtype=np.float32)
    second_color = np.asarray(second.get("dominant_color", (255, 255, 255)), dtype=np.float32)
    channel_distance = float(np.max(np.abs(first_color - second_color)))
    if channel_distance <= 42.0:
        return True

    first_saturation = float(first.get("average_saturation", 0.0))
    second_saturation = float(second.get("average_saturation", 0.0))
    if first_saturation <= 55.0 and second_saturation <= 55.0:
        brightness_gap = abs(
            float(first.get("average_brightness", 255.0))
            - float(second.get("average_brightness", 255.0))
        )
        return brightness_gap <= 34.0
    return False


def _is_compact_mixed_color_icon_pair(
    first: dict[str, Any],
    second: dict[str, Any],
    *,
    gap_x: int,
    gap_y: int,
    max_gap: int,
    merged_width: int,
    merged_height: int,
) -> bool:
    if gap_x > max_gap or gap_y > max_gap:
        return False
    if gap_x > 0 and gap_y > 0 and gap_x + gap_y > max_gap:
        return False
    if _looks_like_parallel_line_pair(first, second):
        return False
    aspect_ratio = max(merged_width, merged_height) / max(1, min(merged_width, merged_height))
    if aspect_ratio > 4.5:
        return False
    total_area = int(first["area"]) + int(second["area"])
    return total_area / max(1, merged_width * merged_height) >= 0.12


def _looks_like_simple_line_collection(group: list[dict[str, Any]], merged: dict[str, Any]) -> bool:
    line_members = [_line_orientation(component) for component in group]
    concrete_orientations = [orientation for orientation in line_members if orientation is not None]
    if len(concrete_orientations) < len(group):
        return False

    orientation_set = set(concrete_orientations)
    width = _component_width(merged)
    height = _component_height(merged)
    aspect_ratio = max(width, height) / max(1, min(width, height))
    if len(orientation_set) == 1:
        return True
    return aspect_ratio >= 3.0


def _looks_like_parallel_line_pair(first: dict[str, Any], second: dict[str, Any]) -> bool:
    first_orientation = _line_orientation(first)
    second_orientation = _line_orientation(second)
    return first_orientation is not None and first_orientation == second_orientation


def _line_orientation(component: dict[str, Any]) -> str | None:
    width = _component_width(component)
    height = _component_height(component)
    long_side = max(width, height)
    short_side = min(width, height)
    aspect_ratio = long_side / max(1, short_side)
    area = int(component["area"])
    density = area / max(1, width * height)
    if aspect_ratio < 2.0 or short_side > 14 or density < 0.25:
        return None
    if width >= height * 2:
        return "horizontal"
    return "vertical"


def _component_width(component: dict[str, Any]) -> int:
    return max(1, int(component["right"]) - int(component["left"]))


def _component_height(component: dict[str, Any]) -> int:
    return max(1, int(component["bottom"]) - int(component["top"]))


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
