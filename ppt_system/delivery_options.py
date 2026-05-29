from __future__ import annotations

from typing import Any

from ppt_system.export_layer_mode import (
    OVERLAY_LAYER_MODE,
    SEPARATE_LAYER_MODE,
    normalize_layer_mode,
)


REFERENCE_PPT_DELIVERY_KEY = "reference_ppt"
EDITABLE_PPT_DELIVERY_KEY = "editable_ppt"

OVERLAY_DELIVERY_MODE = "overlay_slides"
SEPARATE_DELIVERY_MODE = "separate_layer_slides"

REFERENCE_PPT_FILENAME = "result.reference_only.pptx"

EDITABLE_PPT_FILENAMES = {
    OVERLAY_LAYER_MODE: "result.editable.overlay.pptx",
    SEPARATE_LAYER_MODE: "result.editable.separate_slides.pptx",
}

EDITABLE_LAYER_MODE_LABELS = {
    OVERLAY_LAYER_MODE: "元素与文字合页",
    SEPARATE_LAYER_MODE: "元素页 + 文字页双页",
}

EDITABLE_LAYER_MODE_DESCRIPTIONS = {
    OVERLAY_LAYER_MODE: "元素和可编辑文字导出到同一页，页数与逻辑页数一致，适合整体改版。",
    SEPARATE_LAYER_MODE: "每个逻辑页拆成相邻两页，第一页放元素资源，第二页放可编辑文字，方便单独修改后手动叠加。",
}


def normalize_editable_delivery_layer_mode(
    value: Any,
    default: str = SEPARATE_LAYER_MODE,
) -> str:
    resolved = normalize_layer_mode(value, default=default)
    if resolved == OVERLAY_LAYER_MODE:
        return OVERLAY_LAYER_MODE
    return SEPARATE_LAYER_MODE


def build_editable_delivery_mode(layer_mode: Any) -> str:
    resolved = normalize_editable_delivery_layer_mode(layer_mode)
    if resolved == OVERLAY_LAYER_MODE:
        return OVERLAY_DELIVERY_MODE
    return SEPARATE_DELIVERY_MODE


def build_editable_delivery_label(layer_mode: Any) -> str:
    resolved = normalize_editable_delivery_layer_mode(layer_mode)
    return EDITABLE_LAYER_MODE_LABELS[resolved]


def build_editable_delivery_description(layer_mode: Any) -> str:
    resolved = normalize_editable_delivery_layer_mode(layer_mode)
    return EDITABLE_LAYER_MODE_DESCRIPTIONS[resolved]


def build_editable_ppt_filename(layer_mode: Any) -> str:
    resolved = normalize_editable_delivery_layer_mode(layer_mode)
    return EDITABLE_PPT_FILENAMES[resolved]
