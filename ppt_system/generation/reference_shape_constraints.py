from __future__ import annotations

from typing import Any


def build_shape_clarity_prompt_lines(
    style_guide: dict[str, Any] | None = None,
    *,
    detail: str = "compact",
) -> list[str]:
    style_guide = style_guide or {}
    normalized_detail = str(detail).strip().lower() or "compact"
    dashed_allowed = _style_prefers_dashed_connectors(style_guide)

    lines = [
        "轮廓约束：优先使用闭合且清晰的卡片、容器、图标和标签外轮廓，边框与背景保持足够对比，不要用模糊发光、弱对比阴影或糊边代替描边。",
        _build_connector_constraint(dashed_allowed),
        "元素约束：透明感可以保留，但元素边际线要明确；少生成边界发虚、边缘融入背景、难以判断外轮廓的形状。",
        "风格平衡：不要把整页都做成厚重硬框，只需要让主要结构、卡片边界和流程关系足够明确。",
    ]
    if normalized_detail == "full":
        return lines
    return lines[:3]


def _build_connector_constraint(dashed_allowed: bool) -> str:
    if dashed_allowed:
        return (
            "连接线约束：可以保留少量虚线连接器，但只用于次级引导，线段长度与间距要均匀清楚；"
            "主要结构、卡片边框和关键箭头优先使用清晰实线或明确描边。"
        )
    return (
        "连接线约束：优先使用清晰实线或明确描边，尽量少用虚线；"
        "如确需虚线，只用于少量次级连接，且线段清楚、间距均匀。"
    )


def _style_prefers_dashed_connectors(style_guide: dict[str, Any]) -> bool:
    style_core = style_guide.get("style_core", {})
    line_style = ""
    if isinstance(style_core, dict):
        line_style = str(style_core.get("line_style", "")).strip()

    candidates = [
        line_style,
        str(style_guide.get("prompt_anchor", "")).strip(),
        " ".join(_normalize_text_list(style_guide.get("element_primitives", []))),
    ]
    for text in candidates:
        lowered = text.lower()
        if "虚线" in text or "dashed" in lowered or "dash" in lowered:
            return True
    return False


def _normalize_text_list(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [str(item).strip() for item in items if str(item).strip()]
