from __future__ import annotations

from typing import Any


REFERENCE_STYLE_ADHERENCE_LEVELS: tuple[str, ...] = ("loose", "balanced", "strict")

REFERENCE_STYLE_ADHERENCE_LABELS: dict[str, str] = {
    "loose": "宽松",
    "balanced": "适度",
    "strict": "严格",
}

_REFERENCE_STYLE_ADHERENCE_PROMPTS: dict[str, tuple[str, str]] = {
    "loose": (
        "优先学习参考图的版芯比例、留白、背景纹理、线条样式、卡片层级和色彩节奏，再围绕本页内容重新设计。",
        "不要照搬某一张参考图的具体版式，只需要保持同系列视觉一致性。",
    ),
    "balanced": (
        "优先解析参考图的版芯比例、留白、背景纹理、线条样式、卡片层级与色彩节奏，将其作为设计的基准约束。",
        "保留适度发挥空间，做到“框架统一、细节鲜活”，避免刻板套用。",
    ),
    "strict": (
        "严格锁定参考图的版芯比例、留白、背景纹理、线条样式、卡片层级和色彩节奏，然后按照这些规则将本页内容填入。",
        "允许按本页信息重新映射模块内容，但不要跳出这套模板的版式语法、视觉节奏与卡片组织方式。",
    ),
}

_REFERENCE_STYLE_PLANNING_GUIDANCE: dict[str, str] = {
    "loose": "优先保持系列感，允许根据页面信息重新组织局部构图与视觉重心。",
    "balanced": "把参考图当成统一框架，在不偏离核心秩序的前提下允许适度变化。",
    "strict": "把参考图当成强约束模板，优先锁定骨架、层级与色彩节奏，再填入本页内容。",
}


def normalize_reference_style_adherence(value: Any, default: str = "balanced") -> str:
    normalized_default = str(default or "balanced").strip().lower()
    if normalized_default not in REFERENCE_STYLE_ADHERENCE_LEVELS:
        normalized_default = "balanced"
    normalized = str(value or "").strip().lower()
    if normalized in REFERENCE_STYLE_ADHERENCE_LEVELS:
        return normalized
    return normalized_default


def get_reference_style_adherence_label(value: Any, default: str = "balanced") -> str:
    normalized = normalize_reference_style_adherence(value, default)
    return REFERENCE_STYLE_ADHERENCE_LABELS[normalized]


def build_reference_style_adherence_prompt_lines(
    value: Any,
    *,
    has_reference_images: bool,
    default: str = "balanced",
) -> list[str]:
    if not has_reference_images:
        return []
    normalized = normalize_reference_style_adherence(value, default)
    return list(_REFERENCE_STYLE_ADHERENCE_PROMPTS[normalized])


def build_reference_style_adherence_planning_guidance(
    value: Any,
    *,
    has_reference_images: bool,
    default: str = "balanced",
) -> str:
    normalized = normalize_reference_style_adherence(value, default)
    label = get_reference_style_adherence_label(normalized, normalized)
    guidance = _REFERENCE_STYLE_PLANNING_GUIDANCE[normalized]
    if has_reference_images:
        return f"参考图约束强度：{label}。{guidance}"
    return f"参考图约束强度：{label}。当前未上传参考图，后续绑定参考图后按该强度生效。"
