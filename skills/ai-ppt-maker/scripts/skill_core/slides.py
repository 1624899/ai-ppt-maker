from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.util import Inches, Pt

from asset_assembly import add_assets_to_slide
from ppt_system.export.editable_charts import add_editable_chart
from ppt_system.export.export_artifact_policy import save_final_presentation_atomically
from ppt_system.export.ppt_calibration_renderer import render_pptx_slides_to_png
from ppt_system.export.reference_preview_export import export_reference_images_to_pptx
from ppt_system.export.text_style_runtime import apply_run_font_family, should_wrap_text

from skill_core.images import selected_pages


DELIVERY_MODES = {"image_only", "overlay", "separate_slides"}


def _color(value: Any, default: str = "FFFFFF") -> RGBColor:
    raw = str(value or default).strip().lstrip("#").upper()
    if len(raw) != 6 or any(char not in "0123456789ABCDEF" for char in raw):
        raise ValueError(f"颜色必须是六位十六进制值：{value}")
    return RGBColor.from_string(raw)


def _new_slide(presentation: Presentation, background_color: str):
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = _color(background_color)
    return slide


def _add_assets(slide, manifest_path: Path, slide_width: float, slide_height: float) -> int:
    if not manifest_path.is_file():
        raise FileNotFoundError(f"元素清单不存在：{manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for asset in manifest.get("assets", []):
        if not (manifest_path.parent / str(asset.get("file", ""))).is_file():
            raise FileNotFoundError(f"元素文件不存在：{asset.get('file')}")
    return add_assets_to_slide(slide, manifest_path, slide_width, slide_height)


def _add_text_box(slide, box: dict[str, Any], canvas_width: int, canvas_height: int, slide_width: float, slide_height: float) -> None:
    left = Inches(float(box["left"]) / canvas_width * slide_width)
    top = Inches(float(box["top"]) / canvas_height * slide_height)
    width = Inches(float(box["width"]) / canvas_width * slide_width)
    height = Inches(float(box["height"]) / canvas_height * slide_height)
    shape = slide.shapes.add_textbox(left, top, width, height)
    shape.fill.background()
    shape.line.fill.background()
    frame = shape.text_frame
    frame.clear()
    frame.auto_size = MSO_AUTO_SIZE.NONE
    frame.margin_left = Pt(0)
    frame.margin_right = Pt(0)
    frame.margin_top = Pt(0)
    frame.margin_bottom = Pt(0)
    frame.vertical_anchor = getattr(MSO_ANCHOR, str(box.get("valign", "TOP")).upper(), MSO_ANCHOR.TOP)
    frame.word_wrap = should_wrap_text(str(box["text"]), float(box["width"]), float(box["height"]), float(box["font_size"]))

    for line_index, line in enumerate(str(box["text"]).split("\n")):
        paragraph = frame.paragraphs[0] if line_index == 0 else frame.add_paragraph()
        paragraph.alignment = getattr(PP_ALIGN, str(box.get("align", "LEFT")).upper(), PP_ALIGN.LEFT)
        paragraph.space_before = Pt(0)
        paragraph.space_after = Pt(0)
        paragraph.line_spacing = 1.0
        run = paragraph.add_run()
        run.text = line
        run.font.size = Pt(float(box["font_size"]))
        run.font.bold = bool(box.get("bold", False))
        run.font.italic = bool(box.get("italic", False))
        run.font.color.rgb = _color(box.get("color"), "222222")
        apply_run_font_family(run, str(box.get("font_name", "Microsoft YaHei")))


def build_presentation(
    project: dict[str, Any],
    work_dir: Path,
    output_path: Path,
    *,
    mode: str = "overlay",
    page_numbers: list[int] | None = None,
) -> dict[str, Any]:
    if mode not in DELIVERY_MODES:
        raise ValueError("不支持的交付模式：" + mode)
    pages = selected_pages(project, page_numbers)
    canvas_width = int(project["canvas"]["width"])
    canvas_height = int(project["canvas"]["height"])
    slide_width = float(project.get("slide_width_inch", 13.333333))
    slide_height = slide_width * canvas_height / canvas_width

    if mode == "image_only":
        reference_pages = [
            {
                "page_no": int(page["page_no"]),
                "image": str((work_dir / f"page_{int(page['page_no']):02d}" / "reference.png").resolve()),
            }
            for page in pages
        ]
        result = export_reference_images_to_pptx(
            reference_pages,
            work_dir,
            output_path,
            image_width=canvas_width,
            image_height=canvas_height,
            slide_width_inch=slide_width,
        )
        return {"output_pptx": str(Path(result["pptx_path"]).resolve()), "logical_pages": len(pages), "slides": len(pages), "mode": mode}

    presentation = Presentation()
    presentation.slide_width = Inches(slide_width)
    presentation.slide_height = Inches(slide_height)
    for page in pages:
        page_no = int(page["page_no"])
        manifest_path = work_dir / f"page_{page_no:02d}" / "assets" / "assets.json"
        background = str(page.get("background_color") or project.get("background_color") or "#FFFFFF")
        asset_slide = _new_slide(presentation, background)
        charts = page.get("charts", [])
        if page.get("elements_image") or not charts:
            _add_assets(asset_slide, manifest_path, slide_width, slide_height)
        if mode == "separate_slides":
            text_slide = _new_slide(presentation, background)
        else:
            text_slide = asset_slide
        for chart in charts:
            add_editable_chart(
                text_slide,
                chart,
                Inches(chart["left"] / canvas_width * slide_width),
                Inches(chart["top"] / canvas_height * slide_height),
                Inches(chart["width"] / canvas_width * slide_width),
                Inches(chart["height"] / canvas_height * slide_height),
            )
        for box in page.get("text_boxes", []):
            _add_text_box(text_slide, box, canvas_width, canvas_height, slide_width, slide_height)

    saved = save_final_presentation_atomically(presentation, output_path)
    return {
        "output_pptx": str(saved.resolve()),
        "logical_pages": len(pages),
        "slides": len(presentation.slides),
        "mode": mode,
    }


def render_delivery_previews(
    pptx_path: Path,
    output_dir: Path,
    *,
    slide_numbers: list[int] | None = None,
) -> dict[str, Any]:
    if os.name != "nt":
        raise RuntimeError("PowerPoint 真实渲染需要 Windows 与本机 PowerPoint。")
    if not pptx_path.is_file():
        raise FileNotFoundError(f"交付文件不存在：{pptx_path}")
    slide_count = len(Presentation(pptx_path).slides)
    numbers = sorted(set(slide_numbers)) if slide_numbers is not None else list(range(1, slide_count + 1))
    if not numbers or numbers[0] < 1 or numbers[-1] > slide_count:
        raise ValueError(f"预览页码必须在交付文件的实际页码范围内（共 {slide_count} 页）。")
    previews = render_pptx_slides_to_png(pptx_path, output_dir, numbers)
    return {
        "input_pptx": str(pptx_path.resolve()),
        "slide_count": slide_count,
        "pages": [
            {"slide_no": number, "preview_png": str(path.resolve())}
            for number, path in zip(numbers, previews)
        ],
    }
