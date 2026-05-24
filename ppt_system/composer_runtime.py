from __future__ import annotations

from dataclasses import dataclass
from typing import Any


MIN_PPT_FONT_SIZE_PT = 1.0
MIN_PPT_SHAPE_SIZE = 1


@dataclass(frozen=True)
class ShapeGeometry:
    left: int
    top: int
    width: int
    height: int


def resolve_text_geometry(text_item: dict[str, Any], scale_x: float, scale_y: float) -> ShapeGeometry | None:
    return _resolve_geometry(text_item, scale_x, scale_y)


def resolve_asset_geometry(asset: dict[str, Any], scale_x: float, scale_y: float) -> ShapeGeometry | None:
    return _resolve_geometry(asset, scale_x, scale_y)


def should_render_text_item(text_item: dict[str, Any]) -> bool:
    text = str(text_item.get("text", "")).strip()
    if not text:
        return False
    return _has_positive_size(text_item)


def resolve_font_size_pt(text_item: dict[str, Any], default_font: dict[str, Any]) -> float:
    raw_font_size = _coerce_float(text_item.get("font_size"))
    if raw_font_size is not None and raw_font_size >= MIN_PPT_FONT_SIZE_PT:
        return raw_font_size

    default_font_size = _coerce_float(default_font.get("font_size"))
    if default_font_size is not None and default_font_size >= MIN_PPT_FONT_SIZE_PT:
        return default_font_size

    return MIN_PPT_FONT_SIZE_PT


def _resolve_geometry(item: dict[str, Any], scale_x: float, scale_y: float) -> ShapeGeometry | None:
    left = _coerce_float(item.get("left"))
    top = _coerce_float(item.get("top"))
    width = _coerce_float(item.get("width"))
    height = _coerce_float(item.get("height"))
    if left is None or top is None or width is None or height is None:
        return None
    if width <= 0 or height <= 0:
        return None

    return ShapeGeometry(
        left=int(left * scale_x),
        top=int(top * scale_y),
        width=max(MIN_PPT_SHAPE_SIZE, int(width * scale_x)),
        height=max(MIN_PPT_SHAPE_SIZE, int(height * scale_y)),
    )


def _has_positive_size(item: dict[str, Any]) -> bool:
    width = _coerce_float(item.get("width"))
    height = _coerce_float(item.get("height"))
    return width is not None and height is not None and width > 0 and height > 0


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
