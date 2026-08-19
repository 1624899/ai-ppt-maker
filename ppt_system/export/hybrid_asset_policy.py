from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_VISUAL_KINDS = {
    "visual",
    "portrait",
    "product",
    "map",
    "pie",
    "chart-panel",
    "collage-item",
}


def should_keep_hybrid_asset(
    asset: Mapping[str, Any],
    page: Mapping[str, Any],
    image_width: int,
    image_height: int,
) -> bool:
    """判断叠加导出中图片资产是否应与原生蓝图同时保留。"""
    canvas_area = max(1, int(image_width)) * max(1, int(image_height))
    box = _box(asset)
    if box is None:
        return False
    left, top, width, height = box
    asset_area = max(0, _number(asset.get("area"), width * height))
    box_area = width * height

    if _inside_visual_region(box, page):
        return True

    area_ratio = asset_area / canvas_area
    box_ratio = box_area / canvas_area
    density = asset_area / max(1, box_area)
    if area_ratio <= 0.01 and box_ratio <= 0.02 and density >= 0.25:
        return True

    structural_span = width >= image_width * 0.35 or height >= image_height * 0.24
    if structural_span and box_ratio >= 0.08:
        return False
    return True


def _inside_visual_region(box: tuple[float, float, float, float], page: Mapping[str, Any]) -> bool:
    blueprint = page.get("native_blueprint", [])
    if not isinstance(blueprint, list):
        return False
    for shape in blueprint:
        if not isinstance(shape, Mapping) or str(shape.get("kind") or "").lower() not in _VISUAL_KINDS:
            continue
        region = _box(shape)
        if region is None:
            continue
        intersection = _intersection_area(box, region)
        if intersection / max(1.0, box[2] * box[3]) >= 0.5:
            return True
    return False


def _box(value: Mapping[str, Any]) -> tuple[float, float, float, float] | None:
    try:
        left = float(value.get("left", 0))
        top = float(value.get("top", 0))
        width = float(value.get("width", 0))
        height = float(value.get("height", 0))
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return left, top, width, height


def _intersection_area(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    x1 = max(left[0], right[0])
    y1 = max(left[1], right[1])
    x2 = min(left[0] + left[2], right[0] + right[2])
    y2 = min(left[1] + left[3], right[1] + right[3])
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)
