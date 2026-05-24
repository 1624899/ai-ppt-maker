from __future__ import annotations

from typing import Any


_LIGHT_BACKGROUND_TOKENS = (
    "白底",
    "白色",
    "浅蓝",
    "浅色",
    "高明度",
    "明亮",
    "light",
    "bright",
)

_DARK_BACKGROUND_TOKENS = (
    "黑底",
    "深色",
    "暗色",
    "深蓝",
    "深背景",
    "dark",
)

_LIGHT_THEME_PALETTE = {
    "title": "163A63",
    "body": "355C7D",
    "caption": "587695",
    "default": "355C7D",
}

_DARK_THEME_PALETTE = {
    "title": "FFFFFF",
    "body": "DDEBFF",
    "caption": "BFD7FF",
    "default": "DDEBFF",
}


def classify_background_tone(text: str) -> str:
    lower = str(text or "").strip().lower()
    if not lower:
        return "unknown"
    if any(token in lower for token in _LIGHT_BACKGROUND_TOKENS):
        return "light"
    if any(token in lower for token in _DARK_BACKGROUND_TOKENS):
        return "dark"
    return "unknown"


def infer_theme_mode(style_guide: dict[str, Any] | None = None) -> str:
    style_guide = style_guide or {}
    style_core = style_guide.get("style_core", {})
    if isinstance(style_core, dict):
        tone = style_core.get("background_tone", "")
        mode = classify_background_tone(str(tone))
        if mode != "unknown":
            return mode

    for key in ("prompt_anchor", "style_name"):
        mode = classify_background_tone(str(style_guide.get(key, "")))
        if mode != "unknown":
            return mode
    return "unknown"


def resolve_text_palette(style_guide: dict[str, Any] | None = None) -> dict[str, str]:
    mode = infer_theme_mode(style_guide)
    if mode == "dark":
        return dict(_DARK_THEME_PALETTE)
    if mode == "light":
        return dict(_LIGHT_THEME_PALETTE)
    return dict(_DARK_THEME_PALETTE)


def apply_text_theme(texts: list[dict[str, Any]], style_guide: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if not isinstance(texts, list):
        return []

    mode = infer_theme_mode(style_guide)
    if mode == "unknown":
        return [dict(item) if isinstance(item, dict) else item for item in texts]

    palette = resolve_text_palette(style_guide)
    themed_texts: list[dict[str, Any]] = []

    for item in texts:
        if not isinstance(item, dict):
            themed_texts.append(item)
            continue

        themed = dict(item)
        role = str(themed.get("role", "")).lower()
        target_color = _resolve_role_color(role, palette)
        current_color = normalize_hex_color(themed.get("color"))

        # 仅在当前颜色与背景明暗冲突时自动纠偏，避免覆盖用户已给出的合理颜色。
        if target_color and _should_recolor(current_color, mode):
            themed["color"] = target_color
        themed_texts.append(themed)

    return themed_texts


def normalize_hex_color(value: Any) -> str:
    text = str(value or "").strip().lstrip("#").upper()
    if len(text) == 3 and all(ch in "0123456789ABCDEF" for ch in text):
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6 or any(ch not in "0123456789ABCDEF" for ch in text):
        return ""
    return text


def is_light_color(value: Any) -> bool:
    color = normalize_hex_color(value)
    if not color:
        return False
    red = int(color[0:2], 16)
    green = int(color[2:4], 16)
    blue = int(color[4:6], 16)
    luminance = (0.299 * red + 0.587 * green + 0.114 * blue) / 255
    return luminance >= 0.62


def _resolve_role_color(role: str, palette: dict[str, str]) -> str:
    if role == "title":
        return palette["title"]
    if role == "body":
        return palette["body"]
    if role in {"caption", "subtitle"}:
        return palette["caption"]
    return ""


def _should_recolor(current_color: str, mode: str) -> bool:
    if not current_color:
        return True
    if mode == "light":
        return is_light_color(current_color)
    if mode == "dark":
        return not is_light_color(current_color)
    return False
