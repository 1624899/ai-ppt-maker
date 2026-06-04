from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from ppt_system.image.manifest_paths import resolve_assets_dir_from_manifest


TEXT_BOX_ARG_INDEX: dict[str, tuple[int, int, int, int]] = {
    "add_text": (2, 3, 4, 5),
    "add_center_text": (2, 3, 4, 5),
    "add_runs": (2, 3, 4, 5),
    "add_text_ref": (3, 4, 5, 6),
    "add_center_text_ref": (3, 4, 5, 6),
}


@dataclass(frozen=True)
class TextAssetOverlapReport:
    total_boxes: int
    overlap_box_count: int
    overlap_ratio: float
    max_overlap_pixels: int
    overlapping_box_indices: list[int]


def extract_text_boxes(page_script: str) -> list[tuple[int, int, int, int]]:
    """从 page_script 里提取文字框，用于遮罩原稿图中的文本区域。"""
    source = str(page_script or "").strip()
    if not source:
        return []

    tree = ast.parse(source, mode="exec")
    boxes: list[tuple[int, int, int, int]] = []
    for node in tree.body:
        if not isinstance(node, ast.Expr):
            continue
        call = node.value
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
            continue
        arg_index = TEXT_BOX_ARG_INDEX.get(call.func.id)
        if arg_index is None:
            continue
        if len(call.args) <= arg_index[-1]:
            continue
        values: list[int] = []
        try:
            for index in arg_index:
                values.append(_coerce_int(ast.literal_eval(call.args[index])))
        except Exception:
            continue
        left, top, width, height = values
        if width <= 0 or height <= 0:
            continue
        boxes.append((left, top, width, height))
    return boxes


def analyze_text_asset_overlaps(
    *,
    manifest_path: Path,
    page_script: str,
    current_adjustments: dict[str, Any] | None = None,
    box_padding: int = 4,
    min_overlap_pixels: int = 24,
) -> TextAssetOverlapReport:
    """检测当前文字框是否与元素贴图发生明显重叠。"""
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    asset_canvas = _compose_asset_canvas(manifest, current_adjustments or {})
    asset_mask = np.array(asset_canvas.getchannel("A")) > 8
    text_boxes = extract_text_boxes(page_script)
    if not text_boxes:
        return TextAssetOverlapReport(
            total_boxes=0,
            overlap_box_count=0,
            overlap_ratio=0.0,
            max_overlap_pixels=0,
            overlapping_box_indices=[],
        )

    height, width = asset_mask.shape
    overlap_box_count = 0
    max_overlap_pixels = 0
    overlapping_box_indices: list[int] = []
    for index, (left, top, box_width, box_height) in enumerate(text_boxes, start=1):
        x1 = max(0, int(left) - int(box_padding))
        y1 = max(0, int(top) - int(box_padding))
        x2 = min(width, int(left + box_width + box_padding))
        y2 = min(height, int(top + box_height + box_padding))
        if x2 <= x1 or y2 <= y1:
            continue
        overlap_pixels = int(asset_mask[y1:y2, x1:x2].sum())
        max_overlap_pixels = max(max_overlap_pixels, overlap_pixels)
        if overlap_pixels >= int(min_overlap_pixels):
            overlap_box_count += 1
            overlapping_box_indices.append(index)

    total_boxes = len(text_boxes)
    overlap_ratio = overlap_box_count / max(1, total_boxes)
    return TextAssetOverlapReport(
        total_boxes=total_boxes,
        overlap_box_count=overlap_box_count,
        overlap_ratio=overlap_ratio,
        max_overlap_pixels=max_overlap_pixels,
        overlapping_box_indices=overlapping_box_indices,
    )


def _compose_asset_canvas(manifest: dict[str, Any], adjustments: dict[str, Any]) -> Image.Image:
    width = max(1, int(manifest.get("image_width", 1) or 1))
    height = max(1, int(manifest.get("image_height", 1) or 1))
    canvas = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    assets_dir = resolve_assets_dir_from_manifest(manifest)
    normalized_adjustments = _normalize_adjustments(adjustments)
    asset_map = dict(normalized_adjustments.get("asset_map", {}))

    for asset in manifest.get("assets", []):
        asset_path = assets_dir / str(asset["file"])
        asset_image = Image.open(asset_path).convert("RGBA")
        left = int(asset["left"])
        top = int(asset["top"])

        per_asset = dict(asset_map.get(str(int(asset.get("index", 0))), {}))
        left = int(per_asset.get("left", left + int(per_asset.get("dx", 0))))
        top = int(per_asset.get("top", top + int(per_asset.get("dy", 0))))
        canvas.alpha_composite(asset_image, (left, top))
    return canvas


def _normalize_adjustments(adjustments: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(adjustments, dict):
        return {}

    normalized: dict[str, Any] = {}
    asset_map: dict[str, dict[str, int]] = {}
    raw_asset_map = adjustments.get("asset_map")
    if isinstance(raw_asset_map, dict):
        for raw_index, raw_plan in raw_asset_map.items():
            if not isinstance(raw_plan, dict):
                continue
            dx = _coerce_int(raw_plan.get("dx"))
            dy = _coerce_int(raw_plan.get("dy"))
            left = raw_plan.get("left")
            top = raw_plan.get("top")
            plan: dict[str, int] = {}
            if left is not None:
                plan["left"] = _coerce_int(left)
            elif dx:
                plan["dx"] = dx
            if top is not None:
                plan["top"] = _coerce_int(top)
            elif dy:
                plan["dy"] = dy
            if plan:
                asset_map[str(raw_index)] = plan
    if asset_map:
        normalized["asset_map"] = asset_map
    return normalized


def _coerce_int(value: Any) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0
