from __future__ import annotations

from typing import Any

import numpy as np
from ppt_system.component_geometry import bbox_center_x, bbox_center_y

def merge_dashed_line_components(
    components: list[dict[str, Any]],
    *,
    max_dash_gap: int,
    min_group_size: int = 3,
) -> list[dict[str, Any]]:
    """仅合并共线短划线簇，避免把普通框体和图标重新并大。"""
    if len(components) <= 1 or int(max_dash_gap) <= 0:
        return components

    groups = _collect_dashed_line_groups(
        components,
        max_dash_gap=int(max_dash_gap),
        min_group_size=max(2, int(min_group_size)),
    )

    if not groups:
        return components

    grouped_ids = {id(member) for group in groups for member in group}
    merged: list[dict[str, Any]] = []
    for component in components:
        if id(component) in grouped_ids:
            continue
        merged.append(component)
    for group in groups:
        orientation = _infer_dash_orientation(group[0]) or "unknown"
        merged.append(
            merge_component_group(
                group,
                contains_anchor=False,
                extra_metadata={
                    "is_dashed_line_group": True,
                    "dash_group_size": len(group),
                    "dash_orientation": orientation,
                },
            )
        )
    return merged


def _is_dash_like_component(component: dict[str, Any]) -> bool:
    width = int(component["right"]) - int(component["left"])
    height = int(component["bottom"]) - int(component["top"])
    long_side = max(width, height)
    short_side = min(width, height)
    if width <= 0 or height <= 0:
        return False
    if long_side < 4 or short_side > 12:
        return False
    if long_side < short_side * 2:
        return False
    area = int(component["area"])
    density = area / max(1, width * height)
    return density >= 0.45


def _infer_dash_orientation(component: dict[str, Any]) -> str | None:
    width = int(component["right"]) - int(component["left"])
    height = int(component["bottom"]) - int(component["top"])
    if width >= height * 2:
        return "horizontal"
    if height >= width * 2:
        return "vertical"
    return None


def _can_join_dashed_group(
    candidate: dict[str, Any],
    group: list[dict[str, Any]],
    *,
    orientation: str,
    max_dash_gap: int,
) -> bool:
    if orientation == "horizontal":
        candidate_left = int(candidate["left"])
        candidate_right = int(candidate["right"])
        candidate_center_y = bbox_center_y(candidate)
        min_left = min(int(item["left"]) for item in group)
        max_right = max(int(item["right"]) for item in group)
        centers = [bbox_center_y(item) for item in group]
        gap_x = max(0, candidate_left - max_right, min_left - candidate_right)
        if gap_x > max_dash_gap:
            return False
        if abs(candidate_center_y - (sum(centers) / len(centers))) > max(4, max_dash_gap // 2):
            return False
        return True

    candidate_top = int(candidate["top"])
    candidate_bottom = int(candidate["bottom"])
    candidate_center_x = bbox_center_x(candidate)
    min_top = min(int(item["top"]) for item in group)
    max_bottom = max(int(item["bottom"]) for item in group)
    centers = [bbox_center_x(item) for item in group]
    gap_y = max(0, candidate_top - max_bottom, min_top - candidate_bottom)
    if gap_y > max_dash_gap:
        return False
    if abs(candidate_center_x - (sum(centers) / len(centers))) > max(4, max_dash_gap // 2):
        return False
    return True


def _collect_dashed_line_groups(
    components: list[dict[str, Any]],
    *,
    max_dash_gap: int,
    min_group_size: int,
) -> list[list[dict[str, Any]]]:
    pending = [component for component in components if _is_dash_like_component(component)]
    if not pending:
        return []

    groups: list[list[dict[str, Any]]] = []
    consumed: set[int] = set()
    ordered = sorted(
        enumerate(pending),
        key=lambda item: (
            _infer_dash_orientation(item[1]) or "",
            _primary_axis_start(item[1]),
            _secondary_axis_center(item[1]),
        ),
    )

    for seed_index, seed in ordered:
        if seed_index in consumed:
            continue
        orientation = _infer_dash_orientation(seed)
        if orientation is None:
            continue
        group = [seed]
        group_indices = [seed_index]
        consumed.add(seed_index)

        changed = True
        while changed:
            changed = False
            for candidate_index, candidate in ordered:
                if candidate_index in consumed:
                    continue
                if _infer_dash_orientation(candidate) != orientation:
                    continue
                if not _can_join_dashed_group(
                    candidate,
                    group,
                    orientation=orientation,
                    max_dash_gap=max_dash_gap,
                ):
                    continue
                group.append(candidate)
                group_indices.append(candidate_index)
                consumed.add(candidate_index)
                changed = True

        if len(group) >= min_group_size:
            groups.append(group)
        else:
            for index in group_indices:
                consumed.discard(index)
    return groups


def _primary_axis_start(component: dict[str, Any]) -> int:
    orientation = _infer_dash_orientation(component)
    if orientation == "vertical":
        return int(component["top"])
    return int(component["left"])


def _secondary_axis_center(component: dict[str, Any]) -> float:
    orientation = _infer_dash_orientation(component)
    if orientation == "vertical":
        return bbox_center_x(component)
    return bbox_center_y(component)


def merge_component_group(
    group: list[dict[str, Any]],
    *,
    contains_anchor: bool | None = None,
    extra_metadata: dict[str, Any] | None = None,
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

    merged_component = {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "area": int(merged_mask.sum()),
        "mask": merged_mask,
        "component_count": merged_component_count,
        "contains_anchor": merged_contains_anchor,
    }
    if isinstance(extra_metadata, dict):
        merged_component.update(extra_metadata)
    return merged_component
