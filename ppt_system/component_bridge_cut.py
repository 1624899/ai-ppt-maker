from __future__ import annotations

from typing import Any

import numpy as np

from ppt_system.component_container_analysis import estimate_component_barrier_mask
from ppt_system.cv_mask_components import find_mask_components


def cut_container_bridges(
    components: list[dict[str, Any]],
    *,
    image_array: np.ndarray,
    bridge_width_limit: int = 4,
    min_fragment_area: int = 12,
) -> list[dict[str, Any]]:
    """把“框体 + icon”之间靠细桥粘住的混合组件保守切开。"""
    result: list[dict[str, Any]] = []
    for component in components:
        split_children = split_component_near_container_bridge(
            component,
            image_array=image_array,
            bridge_width_limit=int(bridge_width_limit),
            min_fragment_area=int(min_fragment_area),
        )
        result.extend(split_children)
    return result


def split_component_near_container_bridge(
    component: dict[str, Any],
    *,
    image_array: np.ndarray,
    bridge_width_limit: int,
    min_fragment_area: int,
) -> list[dict[str, Any]]:
    if not bool(component.get("is_container", False)):
        return [component]

    local_mask = np.asarray(component["mask"], dtype=bool)
    if local_mask.ndim != 2 or not np.any(local_mask):
        return [component]

    barrier_mask = estimate_component_barrier_mask(component)
    if not np.any(barrier_mask):
        return [component]

    bridge_candidates = _estimate_bridge_candidates(
        component_mask=local_mask,
        barrier_mask=barrier_mask,
        width_limit=max(1, int(bridge_width_limit)),
    )
    if not bridge_candidates:
        return [component]

    accepted_bridge_mask = np.zeros(local_mask.shape, dtype=bool)
    working_mask = np.array(local_mask, copy=True)
    for bridge_mask in bridge_candidates:
        candidate_mask = working_mask & ~bridge_mask
        children = _build_children_from_local_mask(
            component,
            local_mask=candidate_mask,
            image_array=image_array,
            min_fragment_area=max(1, int(min_fragment_area)),
        )
        if len(children) <= 1:
            continue
        if not _contains_container_and_non_container(children):
            continue
        accepted_bridge_mask |= bridge_mask
        working_mask = candidate_mask

    if not np.any(accepted_bridge_mask):
        return [component]

    children = _build_children_from_local_mask(
        component,
        local_mask=working_mask,
        image_array=image_array,
        min_fragment_area=max(1, int(min_fragment_area)),
    )
    if len(children) <= 1:
        return [component]
    if not _contains_container_and_non_container(children):
        return [component]
    return children


def _estimate_bridge_candidates(
    *,
    component_mask: np.ndarray,
    barrier_mask: np.ndarray,
    width_limit: int,
) -> list[np.ndarray]:
    bridge_candidates: list[np.ndarray] = []
    non_barrier_mask = component_mask & ~barrier_mask
    if np.any(non_barrier_mask):
        near_barrier = non_barrier_mask & _dilate_mask(barrier_mask, radius=max(1, int(width_limit)))
        for candidate_component in find_mask_components(near_barrier, connectivity=8):
            local_candidate_mask = np.asarray(candidate_component["mask"], dtype=bool)
            candidate_height, candidate_width = local_candidate_mask.shape
            short_side = min(candidate_height, candidate_width)
            if short_side > max(1, int(width_limit) + 1):
                continue
            candidate_mask = np.zeros(component_mask.shape, dtype=bool)
            offset_top = int(candidate_component["top"])
            offset_left = int(candidate_component["left"])
            candidate_mask[
                offset_top : offset_top + local_candidate_mask.shape[0],
                offset_left : offset_left + local_candidate_mask.shape[1],
            ] = local_candidate_mask
            bridge_candidates.append(candidate_mask)

    neighbor_count = _neighbor_count(component_mask)
    skeleton_like = component_mask & (neighbor_count <= 2) & ~barrier_mask
    for candidate_component in find_mask_components(skeleton_like, connectivity=8):
        local_candidate_mask = np.asarray(candidate_component["mask"], dtype=bool)
        candidate_height, candidate_width = local_candidate_mask.shape
        short_side = min(candidate_height, candidate_width)
        if short_side > max(1, int(width_limit)):
            continue
        candidate_mask = np.zeros(component_mask.shape, dtype=bool)
        offset_top = int(candidate_component["top"])
        offset_left = int(candidate_component["left"])
        candidate_mask[
            offset_top : offset_top + local_candidate_mask.shape[0],
            offset_left : offset_left + local_candidate_mask.shape[1],
        ] = local_candidate_mask
        if not _bridge_candidate_touches_barrier(
            candidate_mask=candidate_mask,
            barrier_mask=barrier_mask,
            width_limit=max(1, int(width_limit)),
        ):
            continue
        bridge_candidates.append(candidate_mask)
    return _deduplicate_bridge_candidates(bridge_candidates)


def _build_children_from_local_mask(
    component: dict[str, Any],
    *,
    local_mask: np.ndarray,
    image_array: np.ndarray,
    min_fragment_area: int,
) -> list[dict[str, Any]]:
    top = int(component["top"])
    left = int(component["left"])
    right = int(component["right"])
    bottom = int(component["bottom"])
    parent_crop = np.asarray(image_array[top:bottom, left:right], dtype=np.uint8)
    children: list[dict[str, Any]] = []
    for child_index, child in enumerate(find_mask_components(local_mask, connectivity=4), start=1):
        area = int(child["area"])
        if area < int(min_fragment_area):
            continue
        child_component = dict(child)
        child_component["left"] = left + int(child["left"])
        child_component["top"] = top + int(child["top"])
        child_component["right"] = left + int(child["right"])
        child_component["bottom"] = top + int(child["bottom"])
        child_component["split_parent_bbox"] = (left, top, right, bottom)
        child_component["split_child_index"] = child_index
        child_component["bridge_cut_applied"] = True
        child_component["fill_ratio"] = _local_fill_ratio(child_component)
        child_component["hole_ratio"] = _estimate_local_hole_ratio(np.asarray(child_component["mask"], dtype=bool))
        child_component["border_contact_count"] = _local_border_contact_count(
            np.asarray(child_component["mask"], dtype=bool)
        )
        child_component["dominant_color_vector"] = _estimate_local_color_vector(
            child_component,
            crop=parent_crop,
        )
        child_component["is_container"] = _child_is_container_like(child_component)
        children.append(child_component)
    return children


def _contains_container_and_non_container(children: list[dict[str, Any]]) -> bool:
    container_count = sum(1 for child in children if bool(child.get("is_container", False)))
    return container_count >= 1 and container_count < len(children)


def _bridge_candidate_touches_barrier(
    *,
    candidate_mask: np.ndarray,
    barrier_mask: np.ndarray,
    width_limit: int,
) -> bool:
    resolved_limit = max(1, int(width_limit))
    neighborhood = _dilate_mask(candidate_mask, radius=resolved_limit)
    return bool(np.any(neighborhood & barrier_mask))


def _neighbor_count(mask: np.ndarray) -> np.ndarray:
    binary = np.asarray(mask, dtype=np.uint8)
    padded = np.pad(binary, ((1, 1), (1, 1)), mode="constant", constant_values=0)
    result = np.zeros(mask.shape, dtype=np.int16)
    for dy in range(3):
        for dx in range(3):
            if dy == 1 and dx == 1:
                continue
            result += padded[dy : dy + mask.shape[0], dx : dx + mask.shape[1]]
    return result


def _deduplicate_bridge_candidates(candidates: list[np.ndarray]) -> list[np.ndarray]:
    unique: list[np.ndarray] = []
    for candidate in candidates:
        if not np.any(candidate):
            continue
        duplicated = False
        for existing in unique:
            if existing.shape != candidate.shape:
                continue
            if np.array_equal(existing, candidate):
                duplicated = True
                break
        if not duplicated:
            unique.append(candidate)
    return unique


def _dilate_mask(mask: np.ndarray, *, radius: int) -> np.ndarray:
    expanded = np.asarray(mask, dtype=bool)
    if not np.any(expanded) or int(radius) <= 0:
        return expanded
    result = np.array(expanded, copy=True)
    for _ in range(int(radius)):
        current = np.array(result, copy=True)
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
                shifted[dst_y_start:dst_y_end, dst_x_start:dst_x_end] = current[
                    src_y_start:src_y_end,
                    src_x_start:src_x_end,
                ]
                result |= shifted
    return result


def _local_fill_ratio(component: dict[str, Any]) -> float:
    width = max(1, int(component["right"]) - int(component["left"]))
    height = max(1, int(component["bottom"]) - int(component["top"]))
    return float(int(component["area"]) / max(1, width * height))


def _estimate_local_hole_ratio(mask: np.ndarray) -> float:
    background = ~np.asarray(mask, dtype=bool)
    if not np.any(background):
        return 0.0
    border_background = np.zeros(background.shape, dtype=bool)
    border_background[0, :] = background[0, :]
    border_background[-1, :] = background[-1, :]
    border_background[:, 0] |= background[:, 0]
    border_background[:, -1] |= background[:, -1]
    expanded = _flood_from_seed(background, border_background)
    hole_mask = background & ~expanded
    return float(np.sum(hole_mask) / max(1, mask.shape[0] * mask.shape[1]))


def _flood_from_seed(candidate_mask: np.ndarray, seed_mask: np.ndarray) -> np.ndarray:
    candidate = np.asarray(candidate_mask, dtype=bool)
    result = np.asarray(seed_mask, dtype=bool) & candidate
    if not np.any(result):
        return np.zeros(candidate.shape, dtype=bool)
    queue = list(zip(*np.nonzero(result)))
    while queue:
        y, x = queue.pop()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny = y + dy
            nx = x + dx
            if ny < 0 or nx < 0 or ny >= candidate.shape[0] or nx >= candidate.shape[1]:
                continue
            if not candidate[ny, nx] or result[ny, nx]:
                continue
            result[ny, nx] = True
            queue.append((ny, nx))
    return result


def _local_border_contact_count(mask: np.ndarray) -> int:
    count = 0
    if bool(mask[0, :].any()):
        count += 1
    if bool(mask[-1, :].any()):
        count += 1
    if bool(mask[:, 0].any()):
        count += 1
    if bool(mask[:, -1].any()):
        count += 1
    return count


def _estimate_local_color_vector(component: dict[str, Any], *, crop: np.ndarray) -> np.ndarray:
    local_left = int(component["left"]) - int(component["split_parent_bbox"][0])
    local_top = int(component["top"]) - int(component["split_parent_bbox"][1])
    local_mask = np.asarray(component["mask"], dtype=bool)
    local_crop = crop[
        local_top : local_top + local_mask.shape[0],
        local_left : local_left + local_mask.shape[1],
    ]
    opaque_mask = local_mask & (local_crop[..., 3] > 0)
    if not np.any(opaque_mask):
        return np.array([255.0, 255.0, 255.0], dtype=np.float32)
    pixels = local_crop[opaque_mask][:, :3]
    return np.median(pixels, axis=0).astype(np.float32)


def _child_is_container_like(component: dict[str, Any]) -> bool:
    width = max(1, int(component["right"]) - int(component["left"]))
    height = max(1, int(component["bottom"]) - int(component["top"]))
    fill_ratio = float(component.get("fill_ratio", _local_fill_ratio(component)))
    hole_ratio = float(component.get("hole_ratio", 0.0))
    border_contact_count = int(component.get("border_contact_count", 0))
    if min(width, height) < 16:
        return False
    if border_contact_count < 2:
        return False
    if fill_ratio >= 0.68 and hole_ratio <= 0.01:
        return False
    return bool(
        (hole_ratio >= 0.04 and fill_ratio <= 0.55)
        or (fill_ratio <= 0.3 and border_contact_count >= 3)
    )
