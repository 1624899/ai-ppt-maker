from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from ppt_system.asset_output_dir import prepare_asset_output_dir
from ppt_system.asset_cleaner import has_fill_mask, restore_removed_regions
from ppt_system.component_decomposer import decompose_components
from ppt_system.component_filter import filter_decorative_components
from ppt_system.component_postprocess import absorb_overlapping_fragments, merge_related_components


SPLIT_MODE_CLASSIC = "classic"
SPLIT_MODE_SEMANTIC = "semantic"


def find_components(mask: np.ndarray) -> list[dict[str, Any]]:
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
            x, y = queue.popleft()
            pixels.append((x, y))
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)

            for dx, dy in neighbors:
                nx = x + dx
                ny = y + dy
                if (
                    0 <= nx < width
                    and 0 <= ny < height
                    and mask[ny, nx]
                    and not visited[ny, nx]
                ):
                    visited[ny, nx] = True
                    queue.append((nx, ny))

        component_mask = np.zeros((max_y - min_y + 1, max_x - min_x + 1), dtype=bool)
        for x, y in pixels:
            component_mask[y - min_y, x - min_x] = True

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


def split_transparent_png(
    image_path: Path,
    out_dir: Path,
    alpha_threshold: int = 8,
    min_area: int = 8,
    min_width: int = 0,
    min_height: int = 0,
    padding: int = 0,
    merge_distance: int = 6,
    filter_decorative_fragments: bool = True,
    split_mode: str = SPLIT_MODE_CLASSIC,
) -> dict[str, Any]:
    image = Image.open(image_path).convert("RGBA")
    image_array = np.array(image)
    alpha = np.array(image.getchannel("A"))
    mask = alpha > alpha_threshold
    raw_components = find_components(mask)
    resolved_split_mode = _normalize_split_mode(split_mode)
    components = raw_components
    if resolved_split_mode == SPLIT_MODE_SEMANTIC:
        components = decompose_components(raw_components, image_array=image_array)
    if int(merge_distance) > 0:
        components = merge_related_components(
            components,
            image_width=image.width,
            image_height=image.height,
            merge_distance=merge_distance,
        )
    components = absorb_overlapping_fragments(
        components,
        image_width=image.width,
        image_height=image.height,
    )
    merged_component_count = len(components)
    removed_components: list[dict[str, Any]] = []
    if filter_decorative_fragments:
        components, removed_components = filter_decorative_components(
            components,
            image_width=image.width,
            image_height=image.height,
        )

    prepare_asset_output_dir(out_dir)
    records: list[dict[str, int | str]] = []
    filtered = [
        component
        for component in components
        if _component_meets_size_thresholds(
            component,
            min_area=min_area,
            min_width=min_width,
            min_height=min_height,
        )
    ]
    filtered.sort(
        key=lambda item: (
            int(item["top"]),
            int(item["left"]),
            int(item["right"]) - int(item["left"]),
            int(item["bottom"]) - int(item["top"]),
        )
    )

    for index, component in enumerate(filtered, start=1):
        raw_left = int(component["left"])
        raw_top = int(component["top"])
        raw_right = int(component["right"])
        raw_bottom = int(component["bottom"])
        component_mask = component["mask"]

        left = max(0, raw_left - padding)
        top = max(0, raw_top - padding)
        right = min(image.width, raw_right + padding)
        bottom = min(image.height, raw_bottom + padding)

        crop = image.crop((left, top, right, bottom))
        crop_array = np.array(crop)
        original_crop_array = np.array(crop_array, copy=True)

        # 只保留当前连通域自己的像素，避免大 bbox 把内部小元素重复裁进去。
        keep_mask = np.zeros((bottom - top, right - left), dtype=bool)
        mask_top = raw_top - top
        mask_left = raw_left - left
        keep_mask[
            mask_top : mask_top + component_mask.shape[0],
            mask_left : mask_left + component_mask.shape[1],
        ] = component_mask
        if has_fill_mask(component):
            fill_mask = np.zeros((bottom - top, right - left), dtype=bool)
            component_fill_mask = np.asarray(component["fill_mask"], dtype=bool)
            fill_mask[
                mask_top : mask_top + component_fill_mask.shape[0],
                mask_left : mask_left + component_fill_mask.shape[1],
            ] = component_fill_mask
            crop_array[~keep_mask & ~fill_mask, 3] = 0
            crop_array[fill_mask, 3] = 0
            crop_array[fill_mask] = original_crop_array[fill_mask]
            crop_array[fill_mask, 3] = 0
            crop_array = restore_removed_regions(crop_array, fill_mask=fill_mask)
        else:
            crop_array[~keep_mask, 3] = 0

        filename = f"asset_{index:03d}.png"
        Image.fromarray(crop_array, mode="RGBA").save(out_dir / filename)
        records.append(
            {
                "index": index,
                "file": filename,
                "left": left,
                "top": top,
                "width": right - left,
                "height": bottom - top,
                "area": int(component["area"]),
            }
        )

    manifest = {
        "source_image": str(image_path),
        "image_width": image.width,
        "image_height": image.height,
        "alpha_threshold": alpha_threshold,
        "min_area": min_area,
        "min_width": int(min_width),
        "min_height": int(min_height),
        "padding": padding,
        "merge_distance": int(merge_distance),
        "filter_decorative_fragments": bool(filter_decorative_fragments),
        "split_mode": resolved_split_mode,
        "raw_component_count": len(raw_components),
        "merged_component_count": merged_component_count,
        "filtered_out_count": len(removed_components),
        "count": len(records),
        "assets": records,
    }
    (out_dir / "assets.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def _normalize_split_mode(value: str) -> str:
    mode = str(value or "").strip().lower()
    if mode == SPLIT_MODE_SEMANTIC:
        return SPLIT_MODE_SEMANTIC
    return SPLIT_MODE_CLASSIC


def _component_meets_size_thresholds(
    component: dict[str, Any],
    *,
    min_area: int,
    min_width: int,
    min_height: int,
) -> bool:
    width = int(component["right"]) - int(component["left"])
    height = int(component["bottom"]) - int(component["top"])
    if int(component["area"]) < int(min_area):
        return False
    if width < max(0, int(min_width)):
        return False
    if height < max(0, int(min_height)):
        return False
    return True
