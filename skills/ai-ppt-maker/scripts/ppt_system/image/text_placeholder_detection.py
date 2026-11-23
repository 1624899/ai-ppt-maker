from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil, floor
from pathlib import Path
from typing import Any

import numpy as np
from cv2 import DIST_L2, distanceTransform
from PIL import Image, ImageColor

from ppt_system.image.binary_morphology import morphology_close, morphology_open, rgb_absdiff_to_gray
from ppt_system.image.cv_mask_components import find_mask_components


DEFAULT_SLIDE_WIDTH_INCH = 13.333333


@dataclass(frozen=True)
class TextPlaceholderDetectionOptions:
    diff_threshold: int = 24
    min_area_ratio: float = 0.00002
    min_width_ratio: float = 0.006
    min_height_ratio: float = 0.01
    horizontal_close_ratio: float = 0.035
    vertical_close_ratio: float = 0.006
    padding_ratio: float = 0.006


def detect_text_placeholders(
    reference_image: Path,
    elements_image: Path,
    *,
    slide_width_inch: float = DEFAULT_SLIDE_WIDTH_INCH,
    background_color: str = "#FFFFFF",
    exclude_regions: Sequence[tuple[float, float, float, float]] = (),
    options: TextPlaceholderDetectionOptions | None = None,
) -> dict[str, Any]:
    """从原稿图与去字元素图的差异中估计逐行文字框。"""
    resolved_options = options or TextPlaceholderDetectionOptions()
    reference_rgba = _load_rgba(reference_image)
    elements_rgba = _load_rgba(elements_image, size=(reference_rgba.shape[1], reference_rgba.shape[0]))
    height, width = reference_rgba.shape[:2]

    background = ImageColor.getrgb(background_color)
    diff_mask = build_text_difference_mask(reference_rgba, elements_rgba, background=background, options=resolved_options)
    exclusions = [
        (slice(floor(top), ceil(top + box_height)), slice(floor(left), ceil(left + box_width)))
        for left, top, box_width, box_height in exclude_regions
    ]
    for region in exclusions:
        diff_mask[region] = False
    reference_rgb = _composite_on_background(reference_rgba, background)
    elements_rgb = _composite_on_background(elements_rgba, background)
    line_boxes = _find_line_boxes(diff_mask, exclusions=exclusions, options=resolved_options)

    placeholders: list[dict[str, Any]] = []
    for box in line_boxes:
        ink_left, ink_top, ink_right, ink_bottom = box
        ink = np.s_[ink_top:ink_bottom, ink_left:ink_right]
        left, top, right, bottom = _pad_box(box, width=width, height=height, options=resolved_options)
        local_mask = diff_mask[ink]
        if not np.any(local_mask):
            continue
        line_height = ink_bottom - ink_top
        font_size = _estimate_font_size(
            line_height_px=line_height,
            image_width=width,
            slide_width_inch=slide_width_inch,
        )
        foreground = reference_rgb[ink][local_mask]
        backdrop = elements_rgb[ink][local_mask]
        delta = np.abs(foreground.astype(np.int16) - backdrop).max(axis=1)
        # 优先采样色差较大的笔画内部，降低抗锯齿边缘的影响。
        strong = delta >= np.percentile(delta, 60)
        placeholders.append(
            {
                "id": f"text_{len(placeholders) + 1:02d}",
                "left": int(left),
                "top": int(top),
                "width": int(right - left),
                "height": int(bottom - top),
                "color": _dominant_color(foreground[strong]),
                "background_color": _dominant_color(backdrop),
                "font_size": font_size,
                "align": "CENTER" if abs((ink_left + ink_right - width) / 2) <= width * 0.04 else "LEFT",
                "anchor": "TOP",
                "bold": _estimate_bold(local_mask, line_height),
            }
        )

    return {
        "schema": "ppt_text_placeholders.v2",
        "canvas": {"width": int(width), "height": int(height)},
        "strategy": "reference_minus_elements_cv",
        "placeholders": placeholders,
    }


def save_text_placeholders(
    reference_image: Path,
    elements_image: Path,
    output_path: Path,
    *,
    slide_width_inch: float = DEFAULT_SLIDE_WIDTH_INCH,
    background_color: str = "#FFFFFF",
    exclude_regions: Sequence[tuple[float, float, float, float]] = (),
    options: TextPlaceholderDetectionOptions | None = None,
) -> dict[str, Any]:
    """保存逐行候选，供后续填入原文和归并段落。"""
    result = detect_text_placeholders(
        reference_image,
        elements_image,
        slide_width_inch=slide_width_inch,
        background_color=background_color,
        exclude_regions=exclude_regions,
        options=options,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def build_text_difference_mask(
    reference_rgba: np.ndarray,
    elements_rgba: np.ndarray,
    *,
    background: tuple[int, int, int] = (255, 255, 255),
    options: TextPlaceholderDetectionOptions | None = None,
) -> np.ndarray:
    """构建文字差异 mask，自动兼容透明元素图与轻微抗锯齿差异。"""
    resolved_options = options or TextPlaceholderDetectionOptions()
    reference = _composite_on_background(reference_rgba, background)
    elements = _composite_on_background(elements_rgba, background)
    gray = rgb_absdiff_to_gray(reference, elements)
    mask = gray >= int(resolved_options.diff_threshold)

    kernel_size = max(1, round(min(reference.shape[:2]) * 0.002))
    return morphology_open(
        mask,
        kernel_width=kernel_size,
        kernel_height=kernel_size,
    )


def load_text_placeholders(path: Path) -> dict[str, Any] | None:
    if not Path(path).exists():
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def placeholder_bboxes(placeholders: dict[str, Any] | None) -> list[tuple[int, int, int, int]]:
    if not isinstance(placeholders, dict):
        return []
    boxes: list[tuple[int, int, int, int]] = []
    for item in placeholders.get("placeholders", []):
        if not isinstance(item, dict):
            continue
        left = _coerce_int(item.get("left"))
        top = _coerce_int(item.get("top"))
        width = _coerce_int(item.get("width"))
        height = _coerce_int(item.get("height"))
        if left is None or top is None or width is None or height is None or width <= 0 or height <= 0:
            continue
        boxes.append((left, top, width, height))
    return boxes


def _load_rgba(image_path: Path, *, size: tuple[int, int] | None = None) -> np.ndarray:
    with Image.open(image_path) as image:
        rgba = image.convert("RGBA")
        if size is not None and rgba.size != size:
            rgba = rgba.resize(size, Image.Resampling.BICUBIC)
        return np.asarray(rgba, dtype=np.uint8)


def _composite_on_background(rgba: np.ndarray, background: tuple[int, int, int]) -> np.ndarray:
    rgb = rgba[:, :, :3].astype(np.float32)
    alpha = rgba[:, :, 3:4].astype(np.float32) / 255.0
    return np.rint(rgb * alpha + np.asarray(background) * (1.0 - alpha)).astype(np.uint8)


def _find_line_boxes(
    mask: np.ndarray,
    *,
    exclusions: Sequence[tuple[slice, slice]],
    options: TextPlaceholderDetectionOptions,
) -> list[tuple[int, int, int, int]]:
    height, width = mask.shape[:2]
    close_w = max(3, round(width * options.horizontal_close_ratio))
    close_h = max(1, round(height * options.vertical_close_ratio))
    closed = morphology_close(
        mask,
        kernel_width=close_w,
        kernel_height=close_h,
    )
    # 闭运算可能把间隔填回，重新清空排除区，避免跨过图表或素材边界连接。
    for region in exclusions:
        closed[region] = False
    min_area = max(4, round(width * height * options.min_area_ratio))
    min_width = max(2, round(width * options.min_width_ratio))
    min_height = max(2, round(height * options.min_height_ratio))

    boxes: list[tuple[int, int, int, int]] = []
    for component in find_mask_components(closed.astype(np.uint8), connectivity=8):
        left = int(component["left"])
        top = int(component["top"])
        right = int(component["right"])
        bottom = int(component["bottom"])
        area = int(component["area"])
        if area < min_area or right - left < min_width or bottom - top < min_height:
            continue
        boxes.append((left, top, right, bottom))
    return sorted(boxes, key=lambda item: (item[1], item[0]))


def _pad_box(
    box: tuple[int, int, int, int],
    *,
    width: int,
    height: int,
    options: TextPlaceholderDetectionOptions,
) -> tuple[int, int, int, int]:
    left, top, right, bottom = box
    pad = max(2, round(min(width, height) * options.padding_ratio))
    return (
        max(0, left - pad),
        max(0, top - pad),
        min(width, right + pad),
        min(height, bottom + pad),
    )


def _estimate_font_size(
    *,
    line_height_px: float,
    image_width: int,
    slide_width_inch: float,
) -> float:
    # 字形可见高度通常小于字号对应的行高。
    return round(max(1.0, line_height_px * slide_width_inch * 72 / image_width / 0.8), 1)


def _dominant_color(pixels: np.ndarray) -> str:
    # 按每通道 16 个色阶分组，再用像素中位数恢复主色。
    bins = pixels.astype(np.int32) // 16
    labels = bins @ np.array([256, 16, 1])
    mode = np.bincount(labels).argmax()
    median = np.median(pixels[labels == mode], axis=0).astype(int)
    return "#" + "".join(f"{channel:02X}" for channel in median)


def _estimate_bold(mask: np.ndarray, line_height: float) -> bool:
    # 以较厚笔画的直径占字形高度的比例估算字重。
    distances = distanceTransform(np.pad(mask.astype(np.uint8), 1), DIST_L2, 5)[1:-1, 1:-1]
    return bool((2 * np.percentile(distances[mask], 85) - 1) / line_height >= 0.15)


def _coerce_int(value: Any) -> int | None:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None
