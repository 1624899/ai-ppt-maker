from __future__ import annotations

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageColor

from ppt_system.export.text_style_runtime import DEFAULT_FONT_NAME
from ppt_system.image.asset_output_dir import prepare_asset_output_dir
from ppt_system.image.canvas_normalization import normalize_image_canvas
from ppt_system.image.image_ops import enhance_image, make_transparent
from ppt_system.image.splitter import split_transparent_png
from ppt_system.image.text_placeholder_detection import save_text_placeholders

from skill_core.project import DEFAULT_SLIDE_WIDTH_INCH, page_background, resolve_project_path, selected_pages


CUTOUT_COLOR_DELTA = 24
CUTOUT_TILE_COUNT = 8
CUTOUT_TILE_DIFF_RATIO = 0.12
CUTOUT_LOST_FOREGROUND_RATIO = 0.02


def normalize_references(
    project: dict[str, Any],
    project_path: Path,
    work_dir: Path,
    page_numbers: list[int] | None = None,
) -> list[dict[str, Any]]:
    width = int(project["canvas"]["width"])
    height = int(project["canvas"]["height"])
    results: list[dict[str, Any]] = []
    for page in selected_pages(project, page_numbers):
        page_no = int(page["page_no"])
        source = resolve_project_path(project_path, str(page.get("reference_image", "")))
        if not source.is_file():
            raise FileNotFoundError(f"第 {page_no} 页原稿图不存在：{source}")
        target = work_dir / f"page_{page_no:02d}" / "reference.png"
        result = normalize_image_canvas(
            source,
            target,
            target_width=width,
            target_height=height,
            resize_mode=str(page.get("resize_mode", "auto")),
            background=page_background(project, page),
            flatten=True,
        )
        results.append({"page_no": page_no, "reference_image": str(target.resolve()), "normalization": result.as_dict()})
    return results


def prepare_images(
    project: dict[str, Any],
    project_path: Path,
    work_dir: Path,
    *,
    page_numbers: list[int] | None = None,
    workers: int = 1,
    min_asset_area: int = 8,
    font_name: str | None = None,
) -> list[dict[str, Any]]:
    width = int(project["canvas"]["width"])
    height = int(project["canvas"]["height"])
    slide_width = float(project.get("slide_width_inch", DEFAULT_SLIDE_WIDTH_INCH))
    pages = selected_pages(project, page_numbers)
    normalize_references(project, project_path, work_dir, [int(page["page_no"]) for page in pages])
    pages_with_elements = [page for page in pages if page.get("elements_image") or not page.get("charts")]

    def prepare_page(page: dict[str, Any]) -> dict[str, Any]:
        page_no = int(page["page_no"])
        page_dir = work_dir / f"page_{page_no:02d}"
        source = resolve_project_path(project_path, str(page.get("elements_image", "")))
        if not source.is_file():
            raise FileNotFoundError(f"第 {page_no} 页元素图不存在：{source}")
        elements_path = page_dir / "elements.png"
        background = page_background(project, page)
        normalize_image_canvas(
            source,
            elements_path,
            target_width=width,
            target_height=height,
            resize_mode=str(page.get("elements_resize_mode", "stretch")),
            background=background,
        )
        placeholders_path = page_dir / "text_placeholders.json"
        excluded_regions = [
            (region["left"], region["top"], region["width"], region["height"])
            for region in (*page.get("charts", []), *page.get("text_exclusion_regions", []))
        ]
        placeholders = save_text_placeholders(
            page_dir / "reference.png", elements_path, placeholders_path,
            slide_width_inch=slide_width, background_color=background, exclude_regions=excluded_regions,
        )
        draft_path = page_dir / "text_boxes.draft.json"
        _write_text_box_draft(draft_path, placeholders["placeholders"], (font_name or "").strip() or DEFAULT_FONT_NAME)
        assets_dir = page_dir / "assets"
        cutout_mode = page.get("cutout_mode", "split")
        transparency = {}
        enhanced_path = None
        if cutout_mode == "background_only":
            manifest = _prepare_background_asset(elements_path, assets_dir, width, height)
            for name in ("elements.enhanced.png", "elements.transparent.png"):
                (page_dir / name).unlink(missing_ok=True)
        else:
            enhanced_path = enhance_image(elements_path, page_dir / "elements.enhanced.png")
            transparent = make_transparent(enhanced_path, page_dir / "elements.transparent.png")
            manifest = split_transparent_png(transparent.output_path, assets_dir, min_area=min_asset_area)
            transparency = {
                "transparent_image": str(transparent.output_path.resolve()),
                "transparency_strategy": transparent.strategy,
                "transparency_warning": transparent.warning,
            }
        recomposed_path = page_dir / "assets.recomposed.png"
        warnings = _check_asset_recomposition(
            page_no, elements_path, assets_dir, manifest, background, recomposed_path, enhanced_path=enhanced_path,
        )
        return {
            "page_no": page_no,
            "reference_image": str((page_dir / "reference.png").resolve()),
            "elements_image": str(elements_path.resolve()),
            "cutout_mode": cutout_mode,
            **transparency,
            "placeholders": str(placeholders_path.resolve()),
            "placeholder_count": len(placeholders["placeholders"]),
            "text_boxes_draft": str(draft_path.resolve()),
            "asset_manifest": str((assets_dir / "assets.json").resolve()),
            "asset_count": int(manifest["count"]),
            "recomposed_image": str(recomposed_path.resolve()),
            "warnings": warnings,
        }

    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as executor:
        results = list(executor.map(prepare_page, pages_with_elements))
    return sorted(results, key=lambda item: item["page_no"])


def _write_text_box_draft(path: Path, placeholders: list[dict[str, Any]], font_name: str) -> None:
    fields = ("left", "top", "width", "height", "font_size", "color", "bold", "align")
    boxes = [
        {"text": "", **{field: item[field] for field in fields}, "valign": item["anchor"], "font_name": font_name}
        for item in placeholders
    ]
    path.write_text(json.dumps({"text_boxes": boxes}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _prepare_background_asset(elements_path: Path, assets_dir: Path, width: int, height: int) -> dict[str, Any]:
    prepare_asset_output_dir(assets_dir)
    filename = "asset_001.png"
    shutil.copyfile(elements_path, assets_dir / filename)
    manifest = {
        "source_image": str(elements_path),
        "image_width": width,
        "image_height": height,
        "count": 1,
        "assets": [{"file": filename, "left": 0, "top": 0, "width": width, "height": height}],
    }
    (assets_dir / "assets.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def _check_asset_recomposition(
    page_no: int, elements_path: Path, assets_dir: Path, manifest: dict[str, Any], background: str, output_path: Path,
    *, enhanced_path: Path | None,
) -> list[dict[str, Any]]:
    width, height = manifest["image_width"], manifest["image_height"]
    assets = Image.new("RGBA", (width, height))
    for asset in manifest["assets"]:
        with Image.open(assets_dir / asset["file"]) as source:
            layer = source.convert("RGBA")
        assets.alpha_composite(layer, (asset["left"], asset["top"]))
    base = Image.new("RGBA", assets.size, background)
    recomposed = Image.alpha_composite(base, assets).convert("RGB")
    recomposed.save(output_path)
    with Image.open(elements_path) as source:
        expected = np.asarray(Image.alpha_composite(base, source.convert("RGBA")).convert("RGB"), dtype=np.int16)
    actual = np.asarray(recomposed, dtype=np.int16)
    changed = np.abs(expected - actual).max(axis=2) >= CUTOUT_COLOR_DELTA
    differs_from_base = np.abs(expected - np.asarray(ImageColor.getrgb(background), dtype=np.int16)).max(axis=2)
    foreground = differs_from_base >= CUTOUT_COLOR_DELTA
    erased = foreground & changed & (np.asarray(assets.getchannel("A")) <= 8)
    if enhanced_path is not None:
        # 排除锐化、对比度增强已经造成的像素差异，保留实际透明空洞。
        with Image.open(enhanced_path) as source:
            enhanced = np.asarray(Image.alpha_composite(base, source.convert("RGBA")).convert("RGB"), dtype=np.int16)
        changed &= np.abs(enhanced - actual).max(axis=2) >= CUTOUT_COLOR_DELTA
        changed |= erased
    lost_ratio = int(erased.sum()) / max(1, int(foreground.sum()))
    regions = []
    x_breaks = np.linspace(0, width, min(width, CUTOUT_TILE_COUNT) + 1, dtype=int).tolist()
    y_breaks = np.linspace(0, height, min(height, CUTOUT_TILE_COUNT) + 1, dtype=int).tolist()
    for top, bottom in zip(y_breaks, y_breaks[1:]):
        for left, right in zip(x_breaks, x_breaks[1:]):
            ratio = float(changed[top:bottom, left:right].mean())
            if ratio >= CUTOUT_TILE_DIFF_RATIO:
                regions.append({"bounds": [left, top, right, bottom], "difference_ratio": ratio})
    if not regions and lost_ratio < CUTOUT_LOST_FOREGROUND_RATIO:
        return []
    regions.sort(key=lambda region: region["difference_ratio"], reverse=True)
    return [{
        "code": "cutout_visual_difference",
        "page_no": page_no,
        "canvas_difference_ratio": round(float(changed.mean()), 4),
        "lost_foreground_ratio": round(lost_ratio, 4),
        "regions": regions[:5],
    }]
