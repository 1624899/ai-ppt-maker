from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from ppt_system.binary_morphology import morphology_close, morphology_open, rgb_absdiff_to_gray
from ppt_system.cv_mask_components import find_mask_components


DEFAULT_SLIDE_WIDTH_INCH = 13.333333


@dataclass(frozen=True)
class TextPlaceholderDetectionOptions:
    diff_threshold: int = 24
    min_area_ratio: float = 0.00002
    min_width_ratio: float = 0.006
    min_height_ratio: float = 0.01
    horizontal_close_ratio: float = 0.035
    vertical_close_ratio: float = 0.006
    max_line_gap_ratio: float = 1.8
    padding_ratio: float = 0.006


def detect_text_placeholders(
    reference_image: Path,
    elements_image: Path,
    *,
    slide_width_inch: float = DEFAULT_SLIDE_WIDTH_INCH,
    options: TextPlaceholderDetectionOptions | None = None,
) -> dict[str, Any]:
    """从“完整参考图 - 去文字元素图”的差异中估计文字占位框。"""
    resolved_options = options or TextPlaceholderDetectionOptions()
    reference_rgba = _load_rgba(reference_image)
    elements_rgba = _load_rgba(elements_image, size=(reference_rgba.shape[1], reference_rgba.shape[0]))
    height, width = reference_rgba.shape[:2]

    diff_mask = build_text_difference_mask(reference_rgba, elements_rgba, options=resolved_options)
    line_boxes = _find_line_boxes(diff_mask, options=resolved_options)
    placeholder_boxes = _merge_line_boxes(line_boxes, width=width, height=height, options=resolved_options)

    placeholders: list[dict[str, Any]] = []
    for index, box in enumerate(placeholder_boxes, start=1):
        left, top, right, bottom = _pad_box(box, width=width, height=height, options=resolved_options)
        local_mask = diff_mask[top:bottom, left:right]
        if not np.any(local_mask):
            continue
        ink_box = _tight_bbox(local_mask)
        line_count = _estimate_line_count(local_mask)
        font_size = _estimate_font_size(
            box_height=bottom - top,
            line_count=line_count,
            image_width=width,
            image_height=height,
            slide_width_inch=slide_width_inch,
        )
        placeholders.append(
            {
                "id": f"text_{index:02d}",
                "left": int(left),
                "top": int(top),
                "width": int(right - left),
                "height": int(bottom - top),
                "color": _estimate_text_color(reference_rgba[top:bottom, left:right], local_mask),
                "font_size": font_size,
                "line_count": int(line_count),
                "align": _estimate_align(
                    left=left,
                    width=right - left,
                    ink_box=ink_box,
                    canvas_width=width,
                ),
                "anchor": "TOP",
                "bold": bool(font_size >= 24),
            }
        )

    return {
        "schema": "ppt_text_placeholders.v1",
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
    options: TextPlaceholderDetectionOptions | None = None,
) -> dict[str, Any]:
    """检测并保存 text_placeholders.json，供模型只填文字内容。"""
    result = detect_text_placeholders(
        reference_image,
        elements_image,
        slide_width_inch=slide_width_inch,
        options=options,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def build_text_difference_mask(
    reference_rgba: np.ndarray,
    elements_rgba: np.ndarray,
    *,
    options: TextPlaceholderDetectionOptions | None = None,
) -> np.ndarray:
    """构建文字差异 mask，自动兼容透明元素图与轻微抗锯齿差异。"""
    resolved_options = options or TextPlaceholderDetectionOptions()
    reference = _composite_on_white(reference_rgba)
    elements = _composite_on_white(elements_rgba)
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


def _composite_on_white(rgba: np.ndarray) -> np.ndarray:
    rgb = rgba[:, :, :3].astype(np.float32)
    alpha = rgba[:, :, 3:4].astype(np.float32) / 255.0
    return np.clip(rgb * alpha + 255.0 * (1.0 - alpha), 0, 255).astype(np.uint8)


def _find_line_boxes(mask: np.ndarray, *, options: TextPlaceholderDetectionOptions) -> list[tuple[int, int, int, int]]:
    height, width = mask.shape[:2]
    close_w = max(3, round(width * options.horizontal_close_ratio))
    close_h = max(1, round(height * options.vertical_close_ratio))
    closed = morphology_close(
        mask,
        kernel_width=close_w,
        kernel_height=close_h,
    )
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


def _merge_line_boxes(
    line_boxes: list[tuple[int, int, int, int]],
    *,
    width: int,
    height: int,
    options: TextPlaceholderDetectionOptions,
) -> list[tuple[int, int, int, int]]:
    groups: list[list[tuple[int, int, int, int]]] = []
    for box in line_boxes:
        matched_group: list[tuple[int, int, int, int]] | None = None
        for group in groups:
            if _can_merge_line(group[-1], box, width=width, height=height, options=options):
                matched_group = group
                break
        if matched_group is None:
            groups.append([box])
        else:
            matched_group.append(box)

    merged: list[tuple[int, int, int, int]] = []
    for group in groups:
        left = min(item[0] for item in group)
        top = min(item[1] for item in group)
        right = max(item[2] for item in group)
        bottom = max(item[3] for item in group)
        merged.append((left, top, right, bottom))
    return sorted(merged, key=lambda item: (item[1], item[0]))


def _can_merge_line(
    first: tuple[int, int, int, int],
    second: tuple[int, int, int, int],
    *,
    width: int,
    height: int,
    options: TextPlaceholderDetectionOptions,
) -> bool:
    first_left, first_top, first_right, first_bottom = first
    second_left, second_top, second_right, second_bottom = second
    if second_top < first_top:
        return False
    gap = second_top - first_bottom
    average_height = max(1, ((first_bottom - first_top) + (second_bottom - second_top)) / 2)
    if gap < 0 or gap > average_height * options.max_line_gap_ratio:
        return False
    overlap = min(first_right, second_right) - max(first_left, second_left)
    min_line_width = max(1, min(first_right - first_left, second_right - second_left))
    left_delta = abs(first_left - second_left)
    center_delta = abs((first_left + first_right) / 2 - (second_left + second_right) / 2)
    return (
        overlap / min_line_width >= 0.35
        or left_delta <= width * 0.025
        or center_delta <= width * 0.035
        or gap <= height * 0.01
    )


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


def _tight_bbox(mask: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.where(mask)
    if xs.size == 0 or ys.size == 0:
        return (0, 0, 0, 0)
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def _estimate_line_count(mask: np.ndarray) -> int:
    row_has_ink = np.any(mask, axis=1).astype(np.uint8)
    if not np.any(row_has_ink):
        return 1
    runs = 0
    in_run = False
    for value in row_has_ink:
        if value and not in_run:
            runs += 1
            in_run = True
        elif not value:
            in_run = False
    return max(1, runs)


def _estimate_font_size(
    *,
    box_height: int,
    line_count: int,
    image_width: int,
    image_height: int,
    slide_width_inch: float,
) -> int:
    slide_height_inch = float(slide_width_inch) * int(image_height) / max(1, int(image_width))
    px_to_pt = slide_height_inch * 72.0 / max(1, int(image_height))
    line_height_px = max(1.0, float(box_height) / max(1, int(line_count)))
    return int(max(8, min(72, round(line_height_px * px_to_pt * 0.82))))


def _estimate_text_color(reference_crop_rgba: np.ndarray, mask: np.ndarray) -> str:
    rgb = _composite_on_white(reference_crop_rgba)
    pixels = rgb[np.asarray(mask, dtype=bool)]
    if pixels.size == 0:
        return "000000"
    median = np.median(pixels, axis=0).astype(int)
    return "".join(f"{channel:02X}" for channel in median[:3])


def _estimate_align(
    *,
    left: int,
    width: int,
    ink_box: tuple[int, int, int, int],
    canvas_width: int,
) -> str:
    ink_left, _ink_top, ink_right, _ink_bottom = ink_box
    box_center = left + width / 2
    ink_center = left + (ink_left + ink_right) / 2
    if abs(box_center - canvas_width / 2) <= canvas_width * 0.04 and width >= canvas_width * 0.12:
        return "CENTER"
    if abs(ink_center - box_center) <= max(6, width * 0.08):
        return "CENTER"
    return "LEFT"


def _coerce_int(value: Any) -> int | None:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None
