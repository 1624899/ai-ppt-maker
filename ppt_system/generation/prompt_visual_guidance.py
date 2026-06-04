from __future__ import annotations

from typing import Any


def build_visual_requirement_line(style_notes: str = "", style_guide: dict[str, Any] | None = None) -> str:
    context = describe_visual_context(style_notes, style_guide)
    return f"视觉要求：视觉语言应匹配{context}；元素轮廓明确、层级清楚，图标/logo/icon 可以保留。"


def build_no_reference_visual_guidance(
    style_notes: str = "",
    style_guide: dict[str, Any] | None = None,
    *,
    mode: str = "compact",
) -> str:
    context = describe_visual_context(style_notes, style_guide)
    if mode == "slot_brief":
        return f"围绕本页内容重新组织页面，视觉语言应匹配{context}，保持有序、可读且便于理解的信息呈现。"
    return f"整体视觉语言应匹配{context}；结构清晰、边界明确，留白和信息密度按内容复杂度自适应。"


def build_template_quality_guidance(style_notes: str = "", style_guide: dict[str, Any] | None = None) -> str:
    context = describe_visual_context(style_notes, style_guide)
    return f"整体要像完成度高的主题化 PPT 模板，视觉语言匹配{context}，结构清楚、留白与信息密度协调、边界明确。"


def build_reference_visual_consistency_guidance() -> str:
    return (
        "优先参考上传的风格图，保持整套 PPT 的主色、背景明度和视觉语言一致。"
        "在不偏离整体风格的前提下，可根据本页内容调整模块数量、信息密度和局部构图。"
    )


def describe_visual_context(style_notes: str = "", style_guide: dict[str, Any] | None = None) -> str:
    base = "页面主题、内容性质和目标受众"
    if has_explicit_style_context(style_notes, style_guide):
        return f"{base}，并优先服从已给定的风格说明"
    return f"{base}，不要套用固定领域模板"


def has_explicit_style_context(style_notes: str = "", style_guide: dict[str, Any] | None = None) -> bool:
    if str(style_notes).strip():
        return True
    if not isinstance(style_guide, dict):
        return False

    for key in ("style_name", "prompt_anchor"):
        if str(style_guide.get(key, "")).strip():
            return True

    style_core = style_guide.get("style_core", {})
    if not isinstance(style_core, dict):
        return False
    return any(_has_meaningful_text(value) for value in style_core.values())


def _has_meaningful_text(value: Any) -> bool:
    if isinstance(value, list):
        return any(str(item).strip() for item in value)
    return bool(str(value).strip())
