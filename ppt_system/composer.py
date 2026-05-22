from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Pt


EMU_PER_INCH = 914400


def _emu(value: float) -> int:
    return int(value)


def add_text_box(slide, text_item: dict[str, Any], scale_x: float, scale_y: float, default_font: dict[str, Any]) -> None:
    left = _emu(float(text_item["left"]) * scale_x)
    top = _emu(float(text_item["top"]) * scale_y)
    width = _emu(float(text_item["width"]) * scale_x)
    height = _emu(float(text_item["height"]) * scale_y)
    box = slide.shapes.add_textbox(left, top, width, height)

    # 文字框无填充、无线条，保证只留下可编辑文字。
    box.fill.background()
    box.line.fill.background()

    frame = box.text_frame
    frame.clear()
    frame.margin_left = 0
    frame.margin_right = 0
    frame.margin_top = 0
    frame.margin_bottom = 0
    frame.word_wrap = True

    paragraph = frame.paragraphs[0]
    paragraph.alignment = getattr(PP_ALIGN, str(text_item.get("align", default_font.get("align", "LEFT"))).upper())
    run = paragraph.add_run()
    run.text = str(text_item.get("text", ""))

    font = run.font
    font.name = str(text_item.get("font_name", default_font.get("font_name", "Microsoft YaHei")))
    font.size = Pt(float(text_item.get("font_size", default_font.get("font_size", 24))))
    font.bold = bool(text_item.get("bold", default_font.get("bold", False)))
    font.italic = bool(text_item.get("italic", default_font.get("italic", False)))
    color = str(text_item.get("color", default_font.get("color", "FFFFFF"))).lstrip("#")
    font.color.rgb = RGBColor.from_string(color)


def compose_pptx(project: dict[str, Any], work_dir: Path, output_pptx: Path) -> None:
    prs = Presentation()
    slide_width_inch = float(project.get("slide_width_inch", 13.333333))
    image_width = int(project.get("image_width", 2000))
    image_height = int(project.get("image_height", 1125))
    prs.slide_width = int(slide_width_inch * EMU_PER_INCH)
    prs.slide_height = int(prs.slide_width * image_height / image_width)

    scale_x = prs.slide_width / image_width
    scale_y = prs.slide_height / image_height
    default_font = project.get("default_font", {})

    for page in project["pages"]:
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        page_dir = work_dir / f"page_{int(page['page_no']):02d}"
        assets = json.loads((page_dir / "assets" / "assets.json").read_text(encoding="utf-8"))

        for asset in assets["assets"]:
            asset_path = page_dir / "assets" / str(asset["file"])
            slide.shapes.add_picture(
                str(asset_path),
                _emu(float(asset["left"]) * scale_x),
                _emu(float(asset["top"]) * scale_y),
                width=_emu(float(asset["width"]) * scale_x),
                height=_emu(float(asset["height"]) * scale_y),
            )

        for text_item in page.get("texts", []):
            add_text_box(slide, text_item, scale_x, scale_y, default_font)

    output_pptx.parent.mkdir(parents=True, exist_ok=True)
    prs.save(output_pptx)

