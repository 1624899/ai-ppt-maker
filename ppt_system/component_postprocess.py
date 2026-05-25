from __future__ import annotations

from typing import Any

import numpy as np


def merge_related_components(
    components: list[dict[str, Any]],
    *,
    image_width: int,
    image_height: int,
    merge_distance: int,
    minimum_fragment_group_size: int = 3,
) -> list[dict[str, Any]]:
    distance = max(0, int(merge_distance))
    if distance <= 0 or len(components) <= 1:
        return components

    anchor_groups, fragments = _split_anchor_groups(
        components,
        image_width=image_width,
        image_height=image_height,
    )
    leftover_fragments: list[dict[str, Any]] = []
    for fragment in fragments:
        attached = _attach_fragment_to_anchor_group(
            fragment,
            anchor_groups,
            attach_distance=max(2, distance * 2),
        )
        if not attached:
            leftover_fragments.append(fragment)

    fragment_groups = _group_fragments(
        leftover_fragments,
        fragment_distance=max(1, distance * 2),
        max_group_span=max(96, int(min(image_width, image_height) * 0.2)),
    )

    merged: list[dict[str, Any]] = []
    for group in anchor_groups:
        merged.append(_merge_component_group(group["members"], contains_anchor=True))
    for group in fragment_groups:
        if len(group) >= max(2, int(minimum_fragment_group_size)):
            merged.append(_merge_component_group(group, contains_anchor=False))
        else:
            merged.extend(group)
    return merged


def absorb_overlapping_fragments(
    components: list[dict[str, Any]],
    *,
    image_width: int,
    image_height: int,
) -> list[dict[str, Any]]:
    if len(components) <= 1:
        return components

    absorbed = sorted(components, key=lambda item: int(item["area"]), reverse=True)
    index = len(absorbed) - 1
    while index >= 0:
        candidate = absorbed[index]
        target_index = _find_absorption_target(
            candidate,
            absorbed,
            candidate_index=index,
            image_width=image_width,
            image_height=image_height,
        )
        if target_index is not None:
            absorbed[target_index] = _merge_component_group([absorbed[target_index], candidate])
            absorbed.pop(index)
        index -= 1
    return absorbed


def _split_anchor_groups(
    components: list[dict[str, Any]],
    *,
    image_width: int,
    image_height: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    image_area = max(1, int(image_width) * int(image_height))
    anchor_area_threshold = max(512, int(image_area * 0.001))
    anchor_density_threshold = 0.2

    anchor_groups: list[dict[str, Any]] = []
    fragments: list[dict[str, Any]] = []
    for component in components:
        if _is_anchor_component(
            component,
            anchor_area_threshold=anchor_area_threshold,
            anchor_density_threshold=anchor_density_threshold,
        ):
            anchor_groups.append({"anchor": component, "members": [component]})
        else:
            fragments.append(component)
    return anchor_groups, fragments


def _is_anchor_component(
    component: dict[str, Any],
    *,
    anchor_area_threshold: int,
    anchor_density_threshold: float,
) -> bool:
    area = int(component["area"])
    width = int(component["right"]) - int(component["left"])
    height = int(component["bottom"]) - int(component["top"])
    bbox_area = max(1, width * height)
    density = area / bbox_area
    return area >= anchor_area_threshold and density >= anchor_density_threshold


def _attach_fragment_to_anchor_group(
    fragment: dict[str, Any],
    anchor_groups: list[dict[str, Any]],
    *,
    attach_distance: int,
) -> bool:
    best_group_index: int | None = None
    best_score: tuple[int, int] | None = None
    for index, group in enumerate(anchor_groups):
        if _should_keep_fragment_separate_from_anchor(fragment, group["anchor"]):
            continue
        gap_x, gap_y = _bbox_gap(fragment, group["anchor"])
        if gap_x > attach_distance or gap_y > attach_distance:
            continue
        score = (max(gap_x, gap_y), gap_x + gap_y)
        if best_score is None or score < best_score:
            best_group_index = index
            best_score = score

    if best_group_index is None:
        return False

    anchor_groups[best_group_index]["members"].append(fragment)
    return True


def _should_keep_fragment_separate_from_anchor(
    fragment: dict[str, Any],
    anchor: dict[str, Any],
) -> bool:
    fragment_left = int(fragment["left"])
    fragment_top = int(fragment["top"])
    fragment_right = int(fragment["right"])
    fragment_bottom = int(fragment["bottom"])
    anchor_left = int(anchor["left"])
    anchor_top = int(anchor["top"])
    anchor_right = int(anchor["right"])
    anchor_bottom = int(anchor["bottom"])

    fully_inside = (
        fragment_left >= anchor_left
        and fragment_top >= anchor_top
        and fragment_right <= anchor_right
        and fragment_bottom <= anchor_bottom
    )
    if not fully_inside:
        return False

    anchor_width = max(1, anchor_right - anchor_left)
    anchor_height = max(1, anchor_bottom - anchor_top)
    fragment_width = max(1, fragment_right - fragment_left)
    fragment_height = max(1, fragment_bottom - fragment_top)
    inset_left = fragment_left - anchor_left
    inset_top = fragment_top - anchor_top
    inset_right = anchor_right - fragment_right
    inset_bottom = anchor_bottom - fragment_bottom
    min_inset = min(inset_left, inset_top, inset_right, inset_bottom)
    inset_threshold = max(8, min(anchor_width, anchor_height) // 18)
    fragment_area = int(fragment["area"])
    fragment_bbox_area = max(1, fragment_width * fragment_height)
    fragment_density = fragment_area / fragment_bbox_area
    meaningful_area = fragment_area >= max(48, int(int(anchor["area"]) * 0.003))
    compact_shape = max(fragment_width, fragment_height) <= max(72, min(anchor_width, anchor_height) // 2)

    return min_inset >= inset_threshold and meaningful_area and (fragment_density >= 0.08 or compact_shape)


def _group_fragments(
    fragments: list[dict[str, Any]],
    *,
    fragment_distance: int,
    max_group_span: int,
) -> list[list[dict[str, Any]]]:
    pending = sorted(fragments, key=lambda item: int(item["area"]), reverse=True)
    groups: list[list[dict[str, Any]]] = []

    while pending:
        seed = pending.pop(0)
        group = [seed]
        group_bbox = _component_bbox(seed)
        changed = True
        while changed:
            changed = False
            for index in range(len(pending) - 1, -1, -1):
                candidate = pending[index]
                if not _can_join_fragment_group(
                    candidate,
                    group_bbox,
                    fragment_distance=fragment_distance,
                    max_group_span=max_group_span,
                ):
                    continue
                group.append(candidate)
                group_bbox = _merge_bbox(group_bbox, _component_bbox(candidate))
                pending.pop(index)
                changed = True
        groups.append(group)

    return groups


def _find_absorption_target(
    candidate: dict[str, Any],
    components: list[dict[str, Any]],
    *,
    candidate_index: int,
    image_width: int,
    image_height: int,
) -> int | None:
    if not _is_absorbable_fragment(
        candidate,
        image_width=image_width,
        image_height=image_height,
    ):
        return None

    candidate_area = int(candidate["area"])
    best_index: int | None = None
    best_area = -1
    for index, target in enumerate(components):
        if index == candidate_index:
            continue
        target_area = int(target["area"])
        if target_area < candidate_area * 8:
            continue
        gap_x, gap_y = _bbox_gap(candidate, target)
        if gap_x > 0 or gap_y > 0:
            continue
        if target_area > best_area:
            best_index = index
            best_area = target_area
    return best_index


def _is_absorbable_fragment(
    component: dict[str, Any],
    *,
    image_width: int,
    image_height: int,
) -> bool:
    left = int(component["left"])
    top = int(component["top"])
    right = int(component["right"])
    bottom = int(component["bottom"])
    width = max(1, right - left)
    height = max(1, bottom - top)
    area = int(component["area"])
    density = area / max(1, width * height)

    min_side = min(image_width, image_height)
    image_area = max(1, image_width * image_height)
    near_edge_margin = max(12, int(min_side * 0.015))
    small_area_threshold = max(160, int(image_area * 0.00007))
    sparse_strip_area_threshold = max(120, int(image_area * 0.00018))

    near_edge = (
        left <= near_edge_margin
        or top <= near_edge_margin
        or right >= image_width - near_edge_margin
        or bottom >= image_height - near_edge_margin
    )
    hairline = min(width, height) <= 2
    compact = max(width, height) <= near_edge_margin * 2
    return near_edge and (
        area <= small_area_threshold
        or (density <= 0.045 and area <= sparse_strip_area_threshold)
        or (hairline and compact)
    )


def _can_join_fragment_group(
    candidate: dict[str, Any],
    group_bbox: tuple[int, int, int, int],
    *,
    fragment_distance: int,
    max_group_span: int,
) -> bool:
    gap_x, gap_y = _bbox_gap_from_bbox(_component_bbox(candidate), group_bbox)
    if gap_x > fragment_distance or gap_y > fragment_distance:
        return False

    merged_bbox = _merge_bbox(group_bbox, _component_bbox(candidate))
    width = merged_bbox[2] - merged_bbox[0]
    height = merged_bbox[3] - merged_bbox[1]
    return width <= max_group_span and height <= max_group_span


def _merge_component_group(
    group: list[dict[str, Any]],
    *,
    contains_anchor: bool | None = None,
) -> dict[str, Any]:
    left = min(int(item["left"]) for item in group)
    top = min(int(item["top"]) for item in group)
    right = max(int(item["right"]) for item in group)
    bottom = max(int(item["bottom"]) for item in group)
    merged_mask = np.zeros((bottom - top, right - left), dtype=bool)
    merged_component_count = 0
    merged_contains_anchor = False if contains_anchor is None else bool(contains_anchor)

    for component in group:
        offset_left = int(component["left"]) - left
        offset_top = int(component["top"]) - top
        component_mask = np.asarray(component["mask"], dtype=bool)
        height, width = component_mask.shape
        merged_mask[offset_top : offset_top + height, offset_left : offset_left + width] |= component_mask
        merged_component_count += max(1, int(component.get("component_count", 1)))
        if bool(component.get("contains_anchor", False)):
            merged_contains_anchor = True

    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "area": int(merged_mask.sum()),
        "mask": merged_mask,
        "component_count": merged_component_count,
        "contains_anchor": merged_contains_anchor,
    }


def _bbox_gap(first: dict[str, Any], second: dict[str, Any]) -> tuple[int, int]:
    return _bbox_gap_from_bbox(_component_bbox(first), _component_bbox(second))


def _bbox_gap_from_bbox(
    first: tuple[int, int, int, int],
    second: tuple[int, int, int, int],
) -> tuple[int, int]:
    left_gap = max(0, first[0] - second[2], second[0] - first[2])
    top_gap = max(0, first[1] - second[3], second[1] - first[3])
    return left_gap, top_gap


def _component_bbox(component: dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        int(component["left"]),
        int(component["top"]),
        int(component["right"]),
        int(component["bottom"]),
    )


def _merge_bbox(
    first: tuple[int, int, int, int],
    second: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    return (
        min(first[0], second[0]),
        min(first[1], second[1]),
        max(first[2], second[2]),
        max(first[3], second[3]),
    )
