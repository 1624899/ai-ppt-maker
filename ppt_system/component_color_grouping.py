from __future__ import annotations

from typing import Any

import numpy as np

from ppt_system.component_geometry import bbox_gap, component_bbox, merge_bbox
from ppt_system.component_color_signature import enrich_component_with_color_signature
from ppt_system.component_stroke_features import (
    component_border_contact_count,
    is_colored_stroke_fragment,
    is_vivid_colored_component,
)
from ppt_system.component_postprocess import merge_component_group


def merge_color_coherent_fragments(
    components: list[dict[str, Any]],
    *,
    image_array: np.ndarray,
    image_width: int,
    image_height: int,
    merge_distance: int,
    minimum_group_size: int = 3,
) -> list[dict[str, Any]]:
    distance = max(0, int(merge_distance))
    if distance <= 0 or len(components) <= 1:
        return components

    enriched = [
        enrich_component_with_color_signature(component, image_array=image_array)
        for component in components
    ]
    candidate_indices = [
        index
        for index, component in enumerate(enriched)
        if _is_color_group_candidate(
            component,
            image_width=image_width,
            image_height=image_height,
        )
    ]
    if len(candidate_indices) < max(2, int(minimum_group_size)):
        return components

    visited: set[int] = set()
    groups: list[list[int]] = []
    max_gap = max(12, distance * 4)
    # 颜色描边聚合只面向“局部连续描边链”，避免经由传递相邻把整圈回路串成一个大资产。
    max_group_span = max(120, int(min(image_width, image_height) * 0.2))
    color_tolerance = 28.0

    for seed_index in candidate_indices:
        if seed_index in visited:
            continue
        queue = [seed_index]
        group_indices: list[int] = []
        visited.add(seed_index)
        while queue:
            current_index = queue.pop(0)
            group_indices.append(current_index)
            current_component = enriched[current_index]
            current_group = [enriched[index] for index in group_indices]
            for candidate_index in candidate_indices:
                if candidate_index in visited:
                    continue
                candidate_component = enriched[candidate_index]
                if not _can_join_color_group(
                    current_component,
                    candidate_component,
                    max_gap=max_gap,
                    max_group_span=max_group_span,
                    color_tolerance=color_tolerance,
                ):
                    continue
                if not _can_expand_group_bbox(
                    current_group,
                    candidate_component,
                    max_group_span=max_group_span,
                ):
                    continue
                visited.add(candidate_index)
                queue.append(candidate_index)
        groups.append(group_indices)

    if not groups:
        return components

    grouped_indices: set[int] = set()
    merged_components: list[dict[str, Any]] = []
    for group_indices in groups:
        if len(group_indices) < max(2, int(minimum_group_size)):
            continue
        group_components = [enriched[index] for index in group_indices]
        if not _is_meaningful_color_group(
            group_components,
            max_gap=max_gap,
        ):
            continue
        grouped_indices.update(group_indices)
        group_color = _average_group_color(group_components)
        merged_components.append(
            merge_component_group(
                group_components,
                contains_anchor=False,
                extra_metadata={
                    "is_color_coherent_group": True,
                    "color_group_size": len(group_components),
                    "group_color": group_color,
                },
            )
        )

    if not grouped_indices:
        return components

    result: list[dict[str, Any]] = []
    for index, component in enumerate(enriched):
        if index in grouped_indices:
            continue
        result.append(component)
    result.extend(merged_components)
    return result


def _is_color_group_candidate(
    component: dict[str, Any],
    *,
    image_width: int,
    image_height: int,
) -> bool:
    width = max(1, int(component["right"]) - int(component["left"]))
    height = max(1, int(component["bottom"]) - int(component["top"]))
    area = int(component["area"])
    bbox_area = max(1, width * height)
    density = area / bbox_area
    long_side = max(width, height)
    short_side = min(width, height)
    aspect_ratio = long_side / max(1, short_side)
    image_area = max(1, image_width * image_height)
    max_candidate_area = max(2400, int(image_area * 0.0025))

    if area > max_candidate_area:
        return False
    if long_side < 8:
        return False
    if not is_vivid_colored_component(component):
        return False
    if is_colored_stroke_fragment(component):
        return True
    return density <= 0.3 and aspect_ratio >= 1.6


def _can_join_color_group(
    first: dict[str, Any],
    second: dict[str, Any],
    *,
    max_gap: int,
    max_group_span: int,
    color_tolerance: float,
) -> bool:
    if _dominant_color_distance(first, second) > color_tolerance:
        return False

    gap_x, gap_y = bbox_gap(first, second)
    if gap_x > max_gap or gap_y > max_gap:
        return False
    if gap_x > 0 and gap_y > 0 and gap_x + gap_y > max_gap * 2:
        return False

    merged_bbox = merge_bbox(component_bbox(first), component_bbox(second))
    width = merged_bbox[2] - merged_bbox[0]
    height = merged_bbox[3] - merged_bbox[1]
    return width <= max_group_span and height <= max_group_span


def _is_meaningful_color_group(
    group: list[dict[str, Any]],
    *,
    max_gap: int,
) -> bool:
    bbox = component_bbox(group[0])
    total_area = 0
    line_like_count = 0
    vivid_colored_count = 0
    border_attached_count = 0
    horizontal_like_count = 0
    vertical_like_count = 0
    for component in group:
        bbox = merge_bbox(bbox, component_bbox(component))
        total_area += int(component["area"])
        if _is_line_like_component(component):
            line_like_count += 1
        if is_colored_stroke_fragment(component):
            vivid_colored_count += 1
        if component_border_contact_count(component) >= 2:
            border_attached_count += 1
        orientation = _infer_component_orientation(component)
        if orientation == "horizontal":
            horizontal_like_count += 1
        elif orientation == "vertical":
            vertical_like_count += 1

    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    bbox_area = max(1, width * height)
    density = total_area / bbox_area
    long_side = max(width, height)
    short_side = min(width, height)
    aspect_ratio = long_side / max(1, short_side)
    stroke_member_count = max(line_like_count, vivid_colored_count)
    if stroke_member_count < max(2, len(group) - 1):
        return False
    minimum_span = max(24, max_gap + 12)
    if long_side < minimum_span:
        return False
    if short_side < 4:
        return False

    mixed_orientation = horizontal_like_count >= 2 and vertical_like_count >= 2
    if mixed_orientation:
        # 环状、折线状虚线簇会在整体 bbox 中占更高比例，不能沿用单方向虚线的稀疏度阈值。
        return (
            density <= 0.38
            and short_side >= 10
            and border_attached_count >= 2
            and aspect_ratio <= 2.2
        )
    return density <= 0.22


def _is_line_like_component(component: dict[str, Any]) -> bool:
    width = max(1, int(component["right"]) - int(component["left"]))
    height = max(1, int(component["bottom"]) - int(component["top"]))
    area = int(component["area"])
    density = area / max(1, width * height)
    long_side = max(width, height)
    short_side = min(width, height)
    border_contacts = component_border_contact_count(component)
    return short_side <= 14 and (
        long_side / max(1, short_side) >= 2.0
        or density <= 0.4
        or border_contacts >= 3
    )


def _infer_component_orientation(component: dict[str, Any]) -> str | None:
    width = max(1, int(component["right"]) - int(component["left"]))
    height = max(1, int(component["bottom"]) - int(component["top"]))
    if width >= height * 2:
        return "horizontal"
    if height >= width * 2:
        return "vertical"
    return None


def _average_group_color(group: list[dict[str, Any]]) -> tuple[int, int, int]:
    colors = np.asarray(
        [component.get("dominant_color", (255, 255, 255)) for component in group],
        dtype=np.float32,
    )
    average = colors.mean(axis=0)
    return (
        int(round(float(average[0]))),
        int(round(float(average[1]))),
        int(round(float(average[2]))),
    )


def _dominant_color_distance(first: dict[str, Any], second: dict[str, Any]) -> float:
    first_color = np.asarray(first.get("dominant_color", (255, 255, 255)), dtype=np.float32)
    second_color = np.asarray(second.get("dominant_color", (255, 255, 255)), dtype=np.float32)
    return float(np.max(np.abs(first_color - second_color)))


def _can_expand_group_bbox(
    group: list[dict[str, Any]],
    candidate: dict[str, Any],
    *,
    max_group_span: int,
) -> bool:
    bbox = component_bbox(group[0])
    for component in group[1:]:
        bbox = merge_bbox(bbox, component_bbox(component))
    bbox = merge_bbox(bbox, component_bbox(candidate))
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    return width <= max_group_span and height <= max_group_span
