from __future__ import annotations

import unicodedata

from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement


DEFAULT_FONT_NAME = "Microsoft YaHei"


def apply_run_font_family(run, font_name: str) -> None:
    """同时写入 latin / ea / cs，避免 WPS 或 Office 对中文回退到其他字体。"""
    resolved = str(font_name or "").strip() or DEFAULT_FONT_NAME
    run.font.name = resolved
    r_pr = run._r.get_or_add_rPr()
    for tag in ("a:ea", "a:cs"):
        font = r_pr.find(qn(tag))
        if font is None:
            font = OxmlElement(tag)
            r_pr.insert_element_before(font, "a:cs", "a:sym", "a:hlinkClick", "a:hlinkMouseOver", "a:rtl", "a:extLst")
        font.set("typeface", resolved)


def scale_font_size_pt(font_size_pt: float, *, scale: float) -> float:
    resolved_scale = float(scale) if float(scale) > 0 else 1.0
    scaled = float(font_size_pt) * resolved_scale
    return max(1.0, scaled)


def estimate_text_width_units(text: str) -> float:
    units = 0.0
    for char in str(text):
        if char.isspace():
            units += 0.35
            continue
        if unicodedata.combining(char):
            continue
        if unicodedata.east_asian_width(char) in {"W", "F"}:
            units += 1.0
            continue
        if char.isdigit():
            units += 0.62
            continue
        if char.isalpha():
            units += 0.58 if char.isascii() else 0.9
            continue
        units += 0.55 if char.isascii() else 0.9
    return units


def estimate_text_width_pt(text: str, font_size_pt: float) -> float:
    return estimate_text_width_units(text) * font_size_pt


def should_wrap_text(text: str, width_pt: float, height_pt: float, font_size_pt: float) -> bool:
    """统一按磅判断是否对正文启用自动换行。"""
    if "\n" in text:
        return True
    return height_pt >= font_size_pt * 2.2 and estimate_text_width_pt(text, font_size_pt) > width_pt * 1.05
