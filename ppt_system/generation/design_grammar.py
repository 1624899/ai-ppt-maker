from __future__ import annotations

from typing import Any

ALLOWED_LAYOUT_FAMILIES: set[str] = {
    "grid_n_x_m",
    "timeline_horizontal",
    "timeline_vertical",
    "hub_and_spoke",
    "split_left_right",
    "split_top_bottom",
    "compare_dual_axis",
    "process_horizontal",
    "process_vertical",
    "hero_with_supporting_cards",
}

DEFAULT_STYLE_CORE: dict[str, Any] = {
    "background_tone": "按主题选择浅色或中性底色，保证正文可读",
    "palette": ["主题主色", "辅助强调色", "中性色", "背景色"],
    "title_style": "标题层级清楚，关键词强调方式与主题气质一致",
    "card_style": "信息容器边界明确，圆角、描边和阴影强度按主题适配",
    "icon_style": "图标风格与内容领域一致，保持统一和可识别",
    "line_style": "连接线、箭头和编号关系清晰，样式随版式语义适配",
}

DEFAULT_ELEMENT_PRIMITIVES: list[str] = [
    "rounded_card",
    "value_tag",
    "number_badge",
    "linear_icon",
    "arrow_connector",
    "dashed_feedback_line",
]

DEFAULT_VARIATION_POLICY: dict[str, Any] = {
    "same_layout_max_repeat": 1,
    "min_distinct_layout_families": 3,
    "allow_local_recomposition": True,
}

DEFAULT_NEGATIVE_RULES: list[str] = [
    "不要套用与主题无关的固定行业模板",
    "不要使用干扰阅读的复杂背景",
    "不要让页面之间的视觉语言突然断裂",
]

DEFAULT_LAYOUT_FAMILIES: list[str] = [
    "grid_n_x_m",
    "timeline_horizontal",
    "timeline_vertical",
    "hub_and_spoke",
    "split_left_right",
    "split_top_bottom",
    "compare_dual_axis",
    "process_horizontal",
    "process_vertical",
    "hero_with_supporting_cards",
]


def validate_layout_family(name: str) -> bool:
    return name in ALLOWED_LAYOUT_FAMILIES


_LAYOUT_ALIASES: dict[str, str] = {
    "grid": "grid_n_x_m",
    "table": "grid_n_x_m",
    "matrix": "grid_n_x_m",
    "timeline": "timeline_horizontal",
    "horizontal_timeline": "timeline_horizontal",
    "vertical_timeline": "timeline_vertical",
    "radial": "hub_and_spoke",
    "hub": "hub_and_spoke",
    "spoke": "hub_and_spoke",
    "split": "split_left_right",
    "left_right": "split_left_right",
    "two_column": "split_left_right",
    "top_bottom": "split_top_bottom",
    "stack": "split_top_bottom",
    "compare": "compare_dual_axis",
    "dual_axis": "compare_dual_axis",
    "comparison": "compare_dual_axis",
    "process": "process_horizontal",
    "flow": "process_horizontal",
    "pipeline": "process_horizontal",
    "vertical_process": "process_vertical",
    "hero": "hero_with_supporting_cards",
    "cards": "hero_with_supporting_cards",
    "feature_cards": "hero_with_supporting_cards",
}

_LAYOUT_FAMILY_LIST = list(ALLOWED_LAYOUT_FAMILIES)


def normalize_layout_family_name(name: str) -> str:
    if not name:
        return "grid_n_x_m"
    cleaned = str(name).strip().lower().replace(" ", "_").replace("-", "_")
    cleaned = _strip_number_suffix(cleaned)
    if validate_layout_family(cleaned):
        return cleaned
    if cleaned in _LAYOUT_ALIASES:
        return _LAYOUT_ALIASES[cleaned]
    for key, val in _LAYOUT_ALIASES.items():
        if key in cleaned or cleaned in key:
            return val
    return "grid_n_x_m"


def _strip_number_suffix(name: str) -> str:
    import re
    return re.sub(r"_?\d+$", "", name).strip("_")


def normalize_design_grammar(style_guide: dict[str, Any]) -> dict[str, Any]:
    fallback = _default_grammar()
    style_core = style_guide.get("style_core", {})
    if not isinstance(style_core, dict):
        style_core = {}
    merged_core = {}
    for key, default_val in DEFAULT_STYLE_CORE.items():
        val = style_core.get(key)
        if val:
            merged_core[key] = val
        else:
            merged_core[key] = default_val

    raw_families = style_guide.get("layout_families", [])
    if not isinstance(raw_families, list):
        raw_families = []
    families = []
    seen = set()
    for f in raw_families:
        norm = normalize_layout_family_name(str(f))
        if norm not in seen:
            families.append(norm)
            seen.add(norm)
    if len(families) < 3:
        for f in DEFAULT_LAYOUT_FAMILIES:
            if f not in seen:
                families.append(f)
                seen.add(f)
            if len(families) >= 5:
                break

    element_primitives = style_guide.get("element_primitives", [])
    if not isinstance(element_primitives, list) or not element_primitives:
        element_primitives = list(DEFAULT_ELEMENT_PRIMITIVES)

    variation_policy = style_guide.get("variation_policy", {})
    if not isinstance(variation_policy, dict):
        variation_policy = {}
    merged_policy = dict(DEFAULT_VARIATION_POLICY)
    merged_policy.update(variation_policy)

    negative_rules = style_guide.get("negative_rules", [])
    if not isinstance(negative_rules, list) or not negative_rules:
        negative_rules = list(DEFAULT_NEGATIVE_RULES)

    prompt_anchor = str(style_guide.get("prompt_anchor", "")).strip()
    if not prompt_anchor:
        prompt_anchor = build_prompt_anchor({"style_core": merged_core})

    prompt_compression = str(style_guide.get("prompt_compression", "")).strip()
    if not prompt_compression:
        prompt_compression = "compressed"

    return {
        "source": str(style_guide.get("source", "")).strip(),
        "style_name": str(style_guide.get("style_name", "")).strip(),
        "style_core": merged_core,
        "layout_families": families,
        "element_primitives": element_primitives,
        "variation_policy": merged_policy,
        "negative_rules": negative_rules,
        "prompt_anchor": prompt_anchor,
        "prompt_compression": prompt_compression,
    }


def _default_grammar() -> dict[str, Any]:
    return {
        "source": "fallback",
        "style_name": "通用主题化简报",
        "style_core": dict(DEFAULT_STYLE_CORE),
        "layout_families": list(DEFAULT_LAYOUT_FAMILIES),
        "element_primitives": list(DEFAULT_ELEMENT_PRIMITIVES),
        "variation_policy": dict(DEFAULT_VARIATION_POLICY),
        "negative_rules": list(DEFAULT_NEGATIVE_RULES),
        "prompt_anchor": build_prompt_anchor({"style_core": DEFAULT_STYLE_CORE}),
        "prompt_compression": "compressed",
    }


def build_prompt_anchor(style_guide: dict[str, Any]) -> str:
    core = style_guide.get("style_core", DEFAULT_STYLE_CORE)
    bg = core.get("background_tone", DEFAULT_STYLE_CORE["background_tone"])
    palette = core.get("palette", DEFAULT_STYLE_CORE["palette"])
    title = core.get("title_style", DEFAULT_STYLE_CORE["title_style"])
    card = core.get("card_style", DEFAULT_STYLE_CORE["card_style"])
    if isinstance(palette, list):
        palette_str = "、".join(palette[:3])
    else:
        palette_str = str(palette)
    return f"{bg}，{palette_str}配色，{title}，{card}"


def build_prompt_profile(page: dict[str, Any], style_guide: dict[str, Any]) -> str:
    layout_family = page.get("layout_family", "grid_n_x_m")
    difference = page.get("difference_from_previous", "")
    return compress_style_for_prompt(style_guide, mode="compressed", layout_family_override=layout_family, difference_override=difference)


def compress_style_for_prompt(
    style_guide: dict[str, Any],
    mode: str = "compressed",
    max_chars: int = 1800,
    layout_family_override: str | None = None,
    difference_override: str | None = None,
) -> str:
    if mode == "full":
        return _compress_full(style_guide, max_chars)
    if mode == "core":
        return _compress_core(style_guide, max_chars)
    return _compress_compressed(style_guide, max_chars, layout_family_override, difference_override)


def _compress_full(style_guide: dict[str, Any], max_chars: int) -> str:
    import json
    parts: list[str] = []
    parts.append(f"风格名称：{style_guide.get('style_name', '')}")
    core = style_guide.get("style_core", {})
    if isinstance(core, dict):
        parts.append(f"风格核心：{json.dumps(core, ensure_ascii=False)}")
    parts.append(f"版式家族：{'、'.join(style_guide.get('layout_families', []))}")
    parts.append(f"元素原语：{'、'.join(style_guide.get('element_primitives', []))}")
    policy = style_guide.get("variation_policy", {})
    if isinstance(policy, dict):
        parts.append(f"变化策略：{json.dumps(policy, ensure_ascii=False)}")
    parts.append(f"负面规则：{'；'.join(style_guide.get('negative_rules', []))}")
    parts.append(f"风格锚点：{style_guide.get('prompt_anchor', '')}")
    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars]
    return text


def _compress_core(style_guide: dict[str, Any], max_chars: int) -> str:
    core = style_guide.get("style_core", {})
    parts: list[str] = []
    parts.append(f"风格锚点：{style_guide.get('prompt_anchor', '')}")
    if isinstance(core, dict):
        items = []
        for key in ["background_tone", "palette", "title_style", "card_style", "icon_style", "line_style"]:
            val = core.get(key, "")
            if isinstance(val, list):
                val = "、".join(val)
            if val:
                items.append(str(val))
        if items:
            parts.append(f"核心约束：{'，'.join(items)}")
    families = style_guide.get("layout_families", [])
    if families:
        parts.append(f"版式家族：{'、'.join(families[:6])}")
    elements = style_guide.get("element_primitives", [])
    if elements:
        parts.append(f"元素语言：{'、'.join(elements)}")
    neg = style_guide.get("negative_rules", [])
    if neg:
        parts.append(f"禁止事项：{'；'.join(neg[:4])}")
    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars]
    return text


def _compress_compressed(
    style_guide: dict[str, Any],
    max_chars: int,
    layout_family_override: str | None = None,
    difference_override: str | None = None,
) -> str:
    core = style_guide.get("style_core", {})
    anchor = style_guide.get("prompt_anchor", "")
    bg = core.get("background_tone", "") if isinstance(core, dict) else ""
    palette_val = core.get("palette", []) if isinstance(core, dict) else []
    if isinstance(palette_val, list):
        palette_str = "、".join(palette_val[:4])
    else:
        palette_str = str(palette_val)
    title_s = core.get("title_style", "") if isinstance(core, dict) else ""
    card_s = core.get("card_style", "") if isinstance(core, dict) else ""
    icon_s = core.get("icon_style", "") if isinstance(core, dict) else ""
    line_s = core.get("line_style", "") if isinstance(core, dict) else ""
    layout_family = layout_family_override or "、".join(style_guide.get("layout_families", [])[:3])
    difference = difference_override or "按本页内容重新生成具体构图，不复用前一页布局"
    parts = [
        f"风格锚点：{anchor}",
        f"核心约束：{bg}，{palette_str}，{title_s}，{card_s}，{icon_s}，{line_s}。",
        f"本页骨架：{layout_family}",
        f"差异要求：{difference}",
    ]
    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars]
    return text
