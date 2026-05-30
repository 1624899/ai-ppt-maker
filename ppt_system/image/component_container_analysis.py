from __future__ import annotations

from typing import Any

import numpy as np

from ppt_system.image.cv_mask_components import find_mask_components, flood_mask_from_border, grow_mask_from_seed


def annotate_container_features(
    components: list[dict[str, Any]],
    *,
    image_width: int,
    image_height: int,
) -> list[dict[str, Any]]:
    """为组件补充容器识别特征，后续用于 barrier 构建和实例分组。"""
    annotated: list[dict[str, Any]] = []
    for component in components:
        enriched = dict(component)
        mask = np.asarray(component["mask"], dtype=bool)
        width = max(1, int(component["right"]) - int(component["left"]))
        height = max(1, int(component["bottom"]) - int(component["top"]))
        area = max(1, int(component["area"]))
        fill_ratio = float(area / max(1, width * height))
        border_contact_count = _mask_border_contact_count(mask)
        hole_ratio = _estimate_hole_ratio(mask)
        perimeter_margin = _estimate_perimeter_margin(width=width, height=height, fill_ratio=fill_ratio)
        perimeter_band = _build_perimeter_band(height=height, width=width, margin=perimeter_margin)
        perimeter_occupancy_ratio = float(np.sum(mask & perimeter_band) / area)
        score = _estimate_container_score(
            width=width,
            height=height,
            fill_ratio=fill_ratio,
            hole_ratio=hole_ratio,
            border_contact_count=border_contact_count,
            perimeter_occupancy_ratio=perimeter_occupancy_ratio,
        )
        is_container = _is_container_like(
            width=width,
            height=height,
            fill_ratio=fill_ratio,
            hole_ratio=hole_ratio,
            border_contact_count=border_contact_count,
            perimeter_occupancy_ratio=perimeter_occupancy_ratio,
            score=score,
        )
        enriched.update(
            {
                "fill_ratio": fill_ratio,
                "hole_ratio": hole_ratio,
                "border_contact_count": border_contact_count,
                "perimeter_occupancy_ratio": perimeter_occupancy_ratio,
                "container_score": score,
                "container_perimeter_margin": perimeter_margin,
                "is_container": bool(is_container),
            }
        )
        annotated.append(enriched)
    return annotated


def estimate_component_barrier_mask(component: dict[str, Any]) -> np.ndarray:
    """估计容器组件中真正像框体/边界的像素区域。"""
    mask = np.asarray(component["mask"], dtype=bool)
    if mask.ndim != 2 or not np.any(mask):
        return np.zeros(mask.shape, dtype=bool)

    width = max(1, int(component["right"]) - int(component["left"]))
    height = max(1, int(component["bottom"]) - int(component["top"]))
    fill_ratio = float(component.get("fill_ratio", float(mask.sum()) / max(1, width * height)))
    margin = int(
        component.get(
            "container_perimeter_margin",
            _estimate_perimeter_margin(width=width, height=height, fill_ratio=fill_ratio),
        )
    )
    perimeter_band = _build_perimeter_band(height=height, width=width, margin=margin + 1)
    candidate_mask = mask & perimeter_band
    if not np.any(candidate_mask):
        return np.zeros(mask.shape, dtype=bool)

    border_seed = np.zeros(mask.shape, dtype=bool)
    border_seed[0, :] = candidate_mask[0, :]
    border_seed[-1, :] = candidate_mask[-1, :]
    border_seed[:, 0] |= candidate_mask[:, 0]
    border_seed[:, -1] |= candidate_mask[:, -1]
    if not np.any(border_seed):
        border_seed = candidate_mask

    return grow_mask_from_seed(
        candidate_mask=candidate_mask,
        seed_mask=border_seed,
        connectivity=8,
    )


def build_container_barrier_mask(
    components: list[dict[str, Any]],
    *,
    image_width: int,
    image_height: int,
    dilation_radius: int = 1,
) -> np.ndarray:
    """把容器组件投影回整张图，构建禁止跨越的 barrier mask。"""
    barrier_mask = np.zeros((int(image_height), int(image_width)), dtype=bool)
    for component in components:
        if not bool(component.get("is_container", False)):
            continue
        local_mask = estimate_component_barrier_mask(component)
        if local_mask.ndim != 2 or not np.any(local_mask):
            continue
        top = int(component["top"])
        left = int(component["left"])
        height, width = local_mask.shape
        barrier_mask[top : top + height, left : left + width] |= local_mask
    if int(dilation_radius) > 0:
        return _dilate_mask(barrier_mask, radius=int(dilation_radius))
    return barrier_mask


def annotate_barrier_regions(
    components: list[dict[str, Any]],
    *,
    image_width: int,
    image_height: int,
    barrier_mask: np.ndarray,
) -> list[dict[str, Any]]:
    """标注组件相邻的自由区域，帮助“同框内组团、跨框不合并”。"""
    label_map, exterior_region_ids = _label_free_space_regions(
        barrier_mask=barrier_mask,
        image_width=image_width,
        image_height=image_height,
    )
    annotated: list[dict[str, Any]] = []
    for component in components:
        enriched = dict(component)
        region_counts = _collect_adjacent_region_counts(
            component,
            label_map=label_map,
        )
        adjacent_region_ids = sorted(region_counts.keys())
        enclosed_region_ids = [
            region_id
            for region_id in adjacent_region_ids
            if region_id not in exterior_region_ids
        ]
        primary_region_id = 0
        if region_counts:
            primary_region_id = max(region_counts.items(), key=lambda item: item[1])[0]
        enriched.update(
            {
                "adjacent_region_ids": adjacent_region_ids,
                "enclosed_region_ids": enclosed_region_ids,
                "primary_region_id": int(primary_region_id),
                "adjacent_region_count": len(adjacent_region_ids),
                "adjacent_exterior_region_count": sum(
                    1 for region_id in adjacent_region_ids if region_id in exterior_region_ids
                ),
                "has_enclosed_primary_region": bool(
                    primary_region_id > 0 and primary_region_id not in exterior_region_ids
                ),
            }
        )
        annotated.append(enriched)
    return annotated


def _estimate_container_score(
    *,
    width: int,
    height: int,
    fill_ratio: float,
    hole_ratio: float,
    border_contact_count: int,
    perimeter_occupancy_ratio: float,
) -> float:
    score = 0.0
    if border_contact_count >= 3:
        score += 1.0
    elif border_contact_count >= 2:
        score += 0.45
    if hole_ratio >= 0.08:
        score += 1.2
    elif hole_ratio >= 0.03:
        score += 0.55
    if perimeter_occupancy_ratio >= 0.82:
        score += 1.0
    elif perimeter_occupancy_ratio >= 0.65:
        score += 0.55
    if fill_ratio <= 0.32:
        score += 0.85
    elif fill_ratio <= 0.48:
        score += 0.35
    if min(width, height) >= 20:
        score += 0.35
    return score


def _is_container_like(
    *,
    width: int,
    height: int,
    fill_ratio: float,
    hole_ratio: float,
    border_contact_count: int,
    perimeter_occupancy_ratio: float,
    score: float,
) -> bool:
    min_side = min(width, height)
    if min_side < 16:
        return False
    if border_contact_count < 2:
        return False
    if fill_ratio >= 0.72 and hole_ratio <= 0.01:
        return False
    if score >= 2.6:
        return True
    return bool(
        hole_ratio >= 0.05
        and perimeter_occupancy_ratio >= 0.55
        and fill_ratio <= 0.5
    )


def _estimate_hole_ratio(mask: np.ndarray) -> float:
    background_mask = ~np.asarray(mask, dtype=bool)
    if not np.any(background_mask):
        return 0.0
    border_background = flood_mask_from_border(background_mask, connectivity=4)
    hole_mask = background_mask & ~border_background
    return float(np.sum(hole_mask) / max(1, mask.shape[0] * mask.shape[1]))


def _estimate_perimeter_margin(*, width: int, height: int, fill_ratio: float) -> int:
    min_side = min(int(width), int(height))
    if min_side <= 18:
        return 2
    if fill_ratio <= 0.2:
        return max(2, min(8, int(round(min_side * 0.16))))
    return max(2, min(12, int(round(min_side * 0.2))))


def _build_perimeter_band(*, height: int, width: int, margin: int) -> np.ndarray:
    resolved_margin = max(1, min(int(margin), max(1, min(height, width) // 2)))
    band = np.zeros((int(height), int(width)), dtype=bool)
    band[:resolved_margin, :] = True
    band[-resolved_margin:, :] = True
    band[:, :resolved_margin] = True
    band[:, -resolved_margin:] = True
    return band


def _label_free_space_regions(
    *,
    barrier_mask: np.ndarray,
    image_width: int,
    image_height: int,
) -> tuple[np.ndarray, set[int]]:
    free_space = ~np.asarray(barrier_mask, dtype=bool)
    label_map = np.zeros((int(image_height), int(image_width)), dtype=np.int32)
    components = find_mask_components(free_space, connectivity=4)
    for index, component in enumerate(components, start=1):
        top = int(component["top"])
        left = int(component["left"])
        local_mask = np.asarray(component["mask"], dtype=bool)
        label_map[top : top + local_mask.shape[0], left : left + local_mask.shape[1]][local_mask] = index

    exterior_region_ids = {
        int(label)
        for label in np.unique(
            np.concatenate(
                [
                    label_map[0, :],
                    label_map[-1, :],
                    label_map[:, 0],
                    label_map[:, -1],
                ]
            )
        ).tolist()
        if int(label) > 0
    }
    return label_map, exterior_region_ids


def _collect_adjacent_region_counts(
    component: dict[str, Any],
    *,
    label_map: np.ndarray,
) -> dict[int, int]:
    top = int(component["top"])
    left = int(component["left"])
    right = int(component["right"])
    bottom = int(component["bottom"])
    height, width = label_map.shape
    search_left = max(0, left - 1)
    search_top = max(0, top - 1)
    search_right = min(width, right + 1)
    search_bottom = min(height, bottom + 1)

    local_mask = np.asarray(component["mask"], dtype=bool)
    ring = _dilate_mask(local_mask, radius=1) & ~local_mask
    local_height = search_bottom - search_top
    local_width = search_right - search_left
    placed_mask = np.zeros((local_height, local_width), dtype=bool)
    mask_top = top - search_top
    mask_left = left - search_left
    placed_mask[
        mask_top : mask_top + local_mask.shape[0],
        mask_left : mask_left + local_mask.shape[1],
    ] = ring
    sampled_labels = label_map[search_top:search_bottom, search_left:search_right][placed_mask]
    valid_labels = sampled_labels[sampled_labels > 0]
    if valid_labels.size == 0:
        return {}

    unique, counts = np.unique(valid_labels, return_counts=True)
    return {
        int(region_id): int(count)
        for region_id, count in zip(unique.tolist(), counts.tolist())
        if int(region_id) > 0
    }


def _mask_border_contact_count(mask: np.ndarray) -> int:
    if mask.size == 0:
        return 0
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
