from __future__ import annotations

from typing import Any

import numpy as np


def is_vivid_colored_component(component: dict[str, Any]) -> bool:
    """判断组件是否仍保留明显的有色描边特征，允许存在一定白边或浅色污染。"""
    average_saturation = float(component.get("average_saturation", 0.0))
    average_brightness = float(component.get("average_brightness", 255.0))
    low_saturation_pixel_ratio = float(component.get("low_saturation_pixel_ratio", 1.0))
    vivid_pixel_ratio = float(component.get("vivid_pixel_ratio", 0.0))

    dominant_color = component.get("dominant_color", (255, 255, 255))
    dominant_color_saturation = float(
        component.get("dominant_color_saturation", _color_channel_span(dominant_color))
    )
    dominant_color_brightness = float(
        component.get("dominant_color_brightness", _color_channel_mean(dominant_color))
    )

    # 整体仍然足够鲜艳时，直接视为有色组件。
    if (
        average_saturation >= 145.0
        and average_brightness <= 215.0
        and low_saturation_pixel_ratio <= 0.45
    ):
        return True

    # 对被白边、白点稀释的组件，改看主色是否鲜艳，以及是否仍保留足够比例的鲜艳像素。
    return (
        dominant_color_saturation >= 170.0
        and dominant_color_brightness <= 210.0
        and vivid_pixel_ratio >= 0.28
    )


def is_colored_stroke_fragment(component: dict[str, Any]) -> bool:
    """判断组件是否像一段有编辑价值的有色描边碎段。"""
    if not is_vivid_colored_component(component):
        return False

    width = _component_width(component)
    height = _component_height(component)
    area = int(component["area"])
    bbox_area = max(1, width * height)
    density = area / bbox_area
    long_side = max(width, height)
    short_side = min(width, height)
    aspect_ratio = long_side / max(1, short_side)
    border_contacts = component_border_contact_count(component)

    line_like = (
        short_side <= 14
        and long_side >= 10
        and (aspect_ratio >= 1.7 or density <= 0.7 or border_contacts >= 3)
    )
    compact_connector = (
        24 <= area <= 320
        and 4 <= short_side <= 22
        and long_side <= 28
        and 0.16 <= density <= 0.82
        and border_contacts >= 2
    )
    return line_like or compact_connector


def component_border_contact_count(component: dict[str, Any]) -> int:
    """统计组件像素接触了裁剪框的多少条边，用于识别描边片段。"""
    mask = np.asarray(component["mask"], dtype=bool)
    if mask.size == 0:
        return 0

    contacts = 0
    if bool(mask[0, :].any()):
        contacts += 1
    if bool(mask[-1, :].any()):
        contacts += 1
    if bool(mask[:, 0].any()):
        contacts += 1
    if bool(mask[:, -1].any()):
        contacts += 1
    return contacts


def _component_width(component: dict[str, Any]) -> int:
    return max(1, int(component["right"]) - int(component["left"]))


def _component_height(component: dict[str, Any]) -> int:
    return max(1, int(component["bottom"]) - int(component["top"]))


def _color_channel_span(color: Any) -> float:
    channels = [int(channel) for channel in color[:3]]
    return float(max(channels) - min(channels))


def _color_channel_mean(color: Any) -> float:
    channels = [int(channel) for channel in color[:3]]
    return float(sum(channels) / max(1, len(channels)))
