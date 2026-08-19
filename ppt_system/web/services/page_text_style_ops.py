from __future__ import annotations

from typing import Any


TEXT_STYLE_FIELDS = ("font_name", "font_size", "color", "bold", "italic")


def apply_page_text_layer_edit(page: dict[str, Any], operation_type: str, payload: dict[str, Any]) -> int:
    """仅修改文字层属性，不读取或修改任何图片字段。"""
    texts = page.get("texts", [])
    if not isinstance(texts, list):
        return 0
    changed = 0
    if operation_type == "page_text_style":
        style = payload.get("style") if isinstance(payload.get("style"), dict) else {}
        for item in texts:
            if not isinstance(item, dict):
                continue
            for key in TEXT_STYLE_FIELDS:
                if key in style and item.get(key) != style[key]:
                    item[key] = style[key]
                    changed += 1
        return changed
    align = str(payload.get("align", "LEFT")).upper()
    for item in texts:
        if isinstance(item, dict) and item.get("align") != align:
            item["align"] = align
            changed += 1
    return changed
