from __future__ import annotations

from itertools import combinations
from math import ceil, floor
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageColor

from ppt_system.export.text_style_runtime import estimate_text_width_pt, should_wrap_text
from skill_core.project import DEFAULT_SLIDE_WIDTH_INCH, DEFAULT_TEXT_COLOR, normalize_hex_color, page_background, selected_pages


SAFE_MARGIN_RATIO = 0.02
SIGNIFICANT_OVERLAP_RATIO = 0.20
ESTIMATED_LINE_HEIGHT_RATIO = 1.2
SIZE_ESTIMATE_TOLERANCE = 1.10


def check_text_quality(
    project: dict[str, Any],
    *,
    work_dir: Path | None,
    mode: str,
    page_numbers: list[int] | None,
) -> list[dict[str, Any]]:
    width, height = int(project["canvas"]["width"]), int(project["canvas"]["height"])
    px_to_pt = float(project.get("slide_width_inch", DEFAULT_SLIDE_WIDTH_INCH)) * 72 / width
    margin_x, margin_y = width * SAFE_MARGIN_RATIO, height * SAFE_MARGIN_RATIO
    warnings: list[dict[str, Any]] = []
    for page in selected_pages(project, page_numbers):
        boxes = page.get("text_boxes", [])
        if not boxes:
            continue
        page_no = page["page_no"]
        background = None
        if mode == "separate_slides" or not page.get("elements_image"):
            background = np.asarray(ImageColor.getrgb(page_background(project, page)))
        elif work_dir is None:
            warnings.append({"code": "text_contrast_unchecked", "page_no": page_no, "reason": "missing_work_dir"})
        else:
            path = work_dir / f"page_{page_no:02d}" / "assets.recomposed.png"
            if path.is_file():
                with Image.open(path) as image:
                    if image.size == (width, height):
                        background = np.asarray(image.convert("RGB"))
            if background is None:
                warnings.append({"code": "text_contrast_unchecked", "page_no": page_no, "expected_image": str(path)})

        bounds: list[tuple[float, float, float, float]] = []
        for number, box in enumerate(boxes, start=1):
            left, top, box_width, box_height = (float(box[key]) for key in ("left", "top", "width", "height"))
            right, bottom = left + box_width, top + box_height
            bounds.append((left, top, right, bottom))
            location = {"page_no": page_no, "text_box": number}
            if left < margin_x or top < margin_y or right > width - margin_x or bottom > height - margin_y:
                warnings.append({"code": "text_near_canvas_edge", **location})

            overflow = _estimate_overflow(box["text"], box_width * px_to_pt, box_height * px_to_pt, float(box["font_size"]))
            if overflow:
                warnings.append({"code": "text_estimated_overflow", **location, **overflow})

            if background is not None:
                sample = background
                if background.ndim == 3:
                    sample = background[floor(top):ceil(bottom), floor(left):ceil(right)]
                if sample.size:
                    contrast = _check_contrast(box, sample)
                    if contrast:
                        warnings.append({"code": "text_low_contrast", **location, **contrast})

        for (first, a), (second, b) in combinations(enumerate(bounds, start=1), 2):
            overlap_width = min(a[2], b[2]) - max(a[0], b[0])
            overlap_height = min(a[3], b[3]) - max(a[1], b[1])
            if overlap_width <= 0 or overlap_height <= 0:
                continue
            smaller_area = min((item[2] - item[0]) * (item[3] - item[1]) for item in (a, b))
            ratio = overlap_width * overlap_height / smaller_area
            if ratio >= SIGNIFICANT_OVERLAP_RATIO:
                warnings.append({
                    "code": "text_box_overlap", "page_no": page_no, "text_boxes": [first, second],
                    "smaller_box_overlap_ratio": round(ratio, 4),
                })
    return warnings


def _estimate_overflow(text: str, width_pt: float, height_pt: float, font_size_pt: float) -> dict[str, Any]:
    line_widths = [estimate_text_width_pt(line, font_size_pt) for line in text.split("\n")]
    wraps = should_wrap_text(text, width_pt, height_pt, font_size_pt)
    if wraps:
        # 理想断行的行数下界，真实字体及长单词仍可能增加行数。
        lines = sum(max(1, ceil(line_width / max(width_pt, 0.01) - 0.05)) for line_width in line_widths)
    else:
        lines = len(line_widths)
    needed_height = lines * font_size_pt * ESTIMATED_LINE_HEIGHT_RATIO
    if needed_height > height_pt * SIZE_ESTIMATE_TOLERANCE or (
        not wraps and max(line_widths) > width_pt * SIZE_ESTIMATE_TOLERANCE
    ):
        return {"estimated_lines": lines, "word_wrap": wraps}
    return {}


def _relative_luminance(rgb: np.ndarray) -> np.ndarray:
    srgb = rgb / 255.0
    linear = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
    return linear @ np.array([0.2126, 0.7152, 0.0722])


def _check_contrast(box: dict[str, Any], pixels: np.ndarray) -> dict[str, float]:
    foreground = ImageColor.getrgb(normalize_hex_color(box.get("color") or DEFAULT_TEXT_COLOR))
    text_luminance = _relative_luminance(np.asarray(foreground))
    background_luminance = _relative_luminance(pixels)
    ratios = (np.maximum(text_luminance, background_luminance) + 0.05) / (
        np.minimum(text_luminance, background_luminance) + 0.05
    )
    # 使用第 10 百分位，保留大片低对比区域，减少零星像素误报。
    ratio = float(np.percentile(ratios, 10))
    large_text = float(box["font_size"]) >= (14 if box.get("bold") else 18)
    threshold = 3.0 if large_text else 4.5
    return {"contrast_ratio": round(ratio, 2), "minimum_ratio": threshold} if ratio < threshold else {}
