from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from ppt_system.asset_output_dir import prepare_asset_output_dir
from ppt_system.component_color_signature import annotate_component_color_signatures
from ppt_system.component_color_grouping import merge_color_coherent_fragments
from ppt_system.component_container_analysis import (
    annotate_barrier_regions,
    annotate_container_features,
    build_container_barrier_mask,
)
from ppt_system.component_graph_clustering import (
    merge_structural_components,
    split_suspicious_sparse_components,
)
from ppt_system.component_bridge_cut import cut_container_bridges
from ppt_system.component_icon_grouping import merge_local_icon_fragments
from ppt_system.component_instance_grouping import group_components_into_instances
from ppt_system.component_postprocess import merge_dashed_line_components
from ppt_system.cv_mask_components import find_mask_components, grow_mask_from_seed


DEFAULT_ALPHA_CORE_THRESHOLD = 48


def split_transparent_png(
    image_path: Path,
    out_dir: Path,
    alpha_threshold: int = 8,
    alpha_core_threshold: int = DEFAULT_ALPHA_CORE_THRESHOLD,
    min_area: int = 8,
    min_width: int = 0,
    min_height: int = 0,
    padding: int = 0,
    merge_distance: int = 6,
) -> dict[str, Any]:
    image = Image.open(image_path).convert("RGBA")
    image_array = np.array(image, dtype=np.uint8)
    image = Image.fromarray(image_array, mode="RGBA")
    alpha = image_array[:, :, 3]
    visual_mask = alpha > int(alpha_threshold)
    core_threshold = max(int(alpha_threshold) + 1, int(alpha_core_threshold))
    core_mask = alpha > core_threshold
    raw_components = find_mask_components(core_mask, connectivity=4)
    components = annotate_component_color_signatures(
        raw_components,
        image_array=image_array,
    )
    components = annotate_container_features(
        components,
        image_width=image.width,
        image_height=image.height,
    )
    if int(merge_distance) > 0:
        components = cut_container_bridges(
            components,
            image_array=image_array,
        )
        components = annotate_component_color_signatures(
            components,
            image_array=image_array,
        )
        components = annotate_container_features(
            components,
            image_width=image.width,
            image_height=image.height,
        )
        barrier_mask = build_container_barrier_mask(
            components,
            image_width=image.width,
            image_height=image.height,
        )
        components = annotate_barrier_regions(
            components,
            image_width=image.width,
            image_height=image.height,
            barrier_mask=barrier_mask,
        )
        components = group_components_into_instances(
            components,
            image_width=image.width,
            image_height=image.height,
            merge_distance=merge_distance,
        )
        components = annotate_component_color_signatures(
            components,
            image_array=image_array,
        )
        components = annotate_container_features(
            components,
            image_width=image.width,
            image_height=image.height,
        )
        components = merge_structural_components(
            components,
            image_array=image_array,
            merge_distance=merge_distance,
        )
        components = merge_dashed_line_components(
            components,
            max_dash_gap=max(4, int(merge_distance) * 2),
        )
        components = merge_color_coherent_fragments(
            components,
            image_array=image_array,
            image_width=image.width,
            image_height=image.height,
            merge_distance=merge_distance,
        )
    components = split_suspicious_sparse_components(
        components,
        image_array=image_array,
    )
    components = annotate_component_color_signatures(
        components,
        image_array=image_array,
    )
    components = merge_local_icon_fragments(
        components,
        image_array=image_array,
        image_width=image.width,
        image_height=image.height,
        merge_distance=merge_distance,
    )
    components = annotate_component_color_signatures(
        components,
        image_array=image_array,
    )
    merged_component_count = len(components)

    prepare_asset_output_dir(out_dir)
    records: list[dict[str, Any]] = []
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
        visual_component_mask = _expand_component_to_visual_mask(
            component,
            visual_mask=visual_mask,
        )
        visual_top = int(component.get("visual_top", raw_top))
        visual_left = int(component.get("visual_left", raw_left))
        visual_bottom = visual_top + visual_component_mask.shape[0]
        visual_right = visual_left + visual_component_mask.shape[1]

        left = max(0, min(raw_left, visual_left) - padding)
        top = max(0, min(raw_top, visual_top) - padding)
        right = min(image.width, max(raw_right, visual_right) + padding)
        bottom = min(image.height, max(raw_bottom, visual_bottom) + padding)

        crop = image.crop((left, top, right, bottom))
        crop_array = np.array(crop)

        # 只保留当前连通域自己的像素，避免大 bbox 把内部小元素重复裁进去。
        keep_mask = np.zeros((bottom - top, right - left), dtype=bool)
        mask_top = visual_top - top
        mask_left = visual_left - left
        keep_mask[
            mask_top : mask_top + visual_component_mask.shape[0],
            mask_left : mask_left + visual_component_mask.shape[1],
        ] = visual_component_mask
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
        "assets_dir": str(out_dir),
        "image_width": image.width,
        "image_height": image.height,
        "alpha_threshold": alpha_threshold,
        "alpha_core_threshold": int(alpha_core_threshold),
        "min_area": min_area,
        "min_width": int(min_width),
        "min_height": int(min_height),
        "padding": padding,
        "merge_distance": int(merge_distance),
        "raw_component_count": len(raw_components),
        "merged_component_count": merged_component_count,
        "count": len(records),
        "assets": records,
    }
    (out_dir / "assets.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


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

    width_threshold = max(0, int(min_width))
    height_threshold = max(0, int(min_height))
    if width_threshold > 0 and height_threshold > 0:
        # 只过滤宽高都偏小的碎块，避免把细长但有编辑价值的线条误删。
        return not (width < width_threshold and height < height_threshold)
    if width_threshold > 0:
        return width >= width_threshold
    if height_threshold > 0:
        return height >= height_threshold
    return True


def _expand_component_to_visual_mask(
    component: dict[str, Any],
    *,
    visual_mask: np.ndarray,
) -> np.ndarray:
    raw_left = int(component["left"])
    raw_top = int(component["top"])
    raw_right = int(component["right"])
    raw_bottom = int(component["bottom"])
    core_mask = np.asarray(component["mask"], dtype=bool)
    height, width = visual_mask.shape

    search_left = max(0, raw_left - 1)
    search_top = max(0, raw_top - 1)
    search_right = min(width, raw_right + 1)
    search_bottom = min(height, raw_bottom + 1)
    local_visual = visual_mask[search_top:search_bottom, search_left:search_right]
    local_seed = np.zeros(local_visual.shape, dtype=bool)
    seed_top = raw_top - search_top
    seed_left = raw_left - search_left
    local_seed[
        seed_top : seed_top + core_mask.shape[0],
        seed_left : seed_left + core_mask.shape[1],
    ] = core_mask

    expanded = _flood_visual_from_seed(local_visual, local_seed)
    if not bool(np.any(expanded)):
        component["visual_left"] = raw_left
        component["visual_top"] = raw_top
        return core_mask

    ys, xs = np.nonzero(expanded)
    min_x = int(xs.min())
    max_x = int(xs.max()) + 1
    min_y = int(ys.min())
    max_y = int(ys.max()) + 1
    component["visual_left"] = search_left + min_x
    component["visual_top"] = search_top + min_y
    return expanded[min_y:max_y, min_x:max_x]


def _flood_visual_from_seed(local_visual: np.ndarray, local_seed: np.ndarray) -> np.ndarray:
    return grow_mask_from_seed(
        candidate_mask=local_visual,
        seed_mask=local_seed,
        connectivity=8,
    )
