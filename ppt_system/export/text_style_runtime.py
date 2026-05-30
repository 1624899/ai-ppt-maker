from __future__ import annotations

from pptx.oxml.ns import qn


DEFAULT_FONT_NAME = "Microsoft YaHei"


def apply_run_font_family(run, font_name: str) -> None:
    """同时写入 latin / ea / cs，避免 WPS 或 Office 对中文回退到其他字体。"""
    resolved = str(font_name or "").strip() or DEFAULT_FONT_NAME
    run.font.name = resolved
    r_pr = run._r.get_or_add_rPr()
    r_pr.set(qn("a:ea"), resolved)
    r_pr.set(qn("a:cs"), resolved)
    latin = r_pr.get_or_add_latin()
    latin.typeface = resolved


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
        codepoint = ord(char)
        if 0x4E00 <= codepoint <= 0x9FFF:
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


def estimate_text_width_px(text: str, font_size_pt: float) -> float:
    return estimate_text_width_units(text) * float(font_size_pt)


def should_wrap_text(text: str, width: float, height: float, font_size_pt: float) -> bool:
    """统一控制单行标签与正文的换行策略。"""
    resolved_text = str(text or "")
    if "\n" in resolved_text:
        return True
    try:
        resolved_width = max(1.0, float(width))
        resolved_height = max(1.0, float(height))
        resolved_size = max(1.0, float(font_size_pt))
    except (TypeError, ValueError):
        return True

    # 高度明显只容纳一行时，优先保持单行并交给自动缩放处理。
    if resolved_height <= resolved_size * 2.4:
        return False
    return estimate_text_width_px(resolved_text, resolved_size) > resolved_width * 1.05
