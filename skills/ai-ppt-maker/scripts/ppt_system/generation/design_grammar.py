from __future__ import annotations

from typing import Any

DEFAULT_STYLE_CORE: dict[str, Any] = {
    "background_tone": "按主题选择浅色或中性底色，保证正文可读",
    "palette": ["主题主色", "辅助强调色", "中性色", "背景色"],
    "title_style": "标题层级清楚，关键词强调方式与主题气质一致",
    "card_style": "信息分组方式随内容语义选择，需要容器时保持边界可辨",
    "icon_style": "图标风格与内容领域一致，保持统一和可识别",
    "line_style": "连接线、箭头和编号关系清晰，样式随版式语义适配",
}

DEFAULT_ELEMENT_PRIMITIVES: list[str] = [
    "语义分组",
    "重点标记",
    "步骤或指标标记",
    "内容匹配图标",
    "关系连接",
    "反馈或依赖提示",
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
    "floor_plan", "magazine_editorial", "full_screen_visual", "circular_cycle", "pyramid_structure", "funnel", "staircase", "progressive_relation", "road_map", "gantt_chart", "cycle_process", "swimlane", "org_chart", "relationship_chain", "venn_relation", "data_cards", "big_number", "dashboard", "bar_chart", "line_chart", "pie_chart", "scatter_plot", "data_table", "map_distribution", "people_profile", "product_showcase", "case_breakdown", "problem_cause_solution", "goal_strategy_action", "summary_detail", "layered_structure", "module_combination", "collage", "tag_categories", "checklist", "milestones", "priority_ranking", "value_chain", "ecosystem", "closed_loop_management", "input_process_output", "three_part", "five_step", "comparison_table", "pros_cons", "swot", "fishbone", "iceberg_model", "tower_structure", "growth_staircase", "route_planning", "annual_plan", "retrospective", "achievement_wall", "scenario_showcase", "scenario_map", "infographic", "visual_metaphor",
]

ALLOWED_LAYOUT_FAMILIES: set[str] = set(DEFAULT_LAYOUT_FAMILIES)

LAYOUT_FAMILY_LABELS: dict[str, str] = {
    "grid_n_x_m": "宫格卡片",
    "timeline_horizontal": "横向时间线",
    "timeline_vertical": "纵向时间线",
    "hub_and_spoke": "中心辐射",
    "split_left_right": "左右分栏",
    "split_top_bottom": "上下分区",
    "compare_dual_axis": "双轴对比",
    "process_horizontal": "横向流程",
    "process_vertical": "纵向流程",
    "hero_with_supporting_cards": "主视觉卡片",
    "floor_plan": "房型图（户型图）", "magazine_editorial": "杂志排版", "full_screen_visual": "全屏视觉", "circular_cycle": "环形循环图", "pyramid_structure": "金字塔结构", "funnel": "漏斗图", "staircase": "阶梯式", "progressive_relation": "递进关系", "road_map": "路径地图（Road Map）", "gantt_chart": "甘特图", "cycle_process": "循环流程图", "swimlane": "泳道图", "org_chart": "组织架构图", "relationship_chain": "关系链路图", "venn_relation": "Venn关系图", "data_cards": "数据卡片", "big_number": "大数字展示", "dashboard": "仪表盘（Dashboard）", "bar_chart": "柱状图分析", "line_chart": "折线趋势图", "pie_chart": "饼图占比", "scatter_plot": "散点分析", "data_table": "数据表格", "map_distribution": "地图分布", "people_profile": "人物介绍", "product_showcase": "产品展示", "case_breakdown": "案例拆解", "problem_cause_solution": "问题—原因—方案", "goal_strategy_action": "目标—策略—行动", "summary_detail": "总分结构", "layered_structure": "分层结构", "module_combination": "模块组合", "collage": "拼贴式", "tag_categories": "标签分类", "checklist": "清单列表", "milestones": "里程碑", "priority_ranking": "优先级排序", "value_chain": "价值链", "ecosystem": "生态圈", "closed_loop_management": "闭环管理", "input_process_output": "输入—过程—输出", "three_part": "三段式", "five_step": "五步法", "comparison_table": "对照表", "pros_cons": "优劣势分析", "swot": "SWOT分析", "fishbone": "鱼骨图", "iceberg_model": "冰山模型", "tower_structure": "塔式结构", "growth_staircase": "阶梯成长", "route_planning": "路径规划", "annual_plan": "年度规划", "retrospective": "复盘总结", "achievement_wall": "成果墙", "scenario_showcase": "场景化展示", "scenario_map": "场景地图", "infographic": "信息图表", "visual_metaphor": "视觉隐喻",
}


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
    "contrast": "compare_dual_axis",
    "process": "process_horizontal",
    "flow": "process_horizontal",
    "pipeline": "process_horizontal",
    "vertical_process": "process_vertical",
    "hero": "hero_with_supporting_cards",
    "cards": "hero_with_supporting_cards",
    "feature_cards": "hero_with_supporting_cards",
    "title_content": "split_top_bottom",
    "title_and_content": "split_top_bottom",
    "cover": "hero_with_supporting_cards",
    "dashboard": "grid_n_x_m",
    "宫格": "grid_n_x_m",
    "宫格卡片": "grid_n_x_m",
    "卡片宫格": "grid_n_x_m",
    "矩阵": "grid_n_x_m",
    "横向时间线": "timeline_horizontal",
    "横向时间轴": "timeline_horizontal",
    "时间线": "timeline_horizontal",
    "时间轴": "timeline_horizontal",
    "纵向时间线": "timeline_vertical",
    "纵向时间轴": "timeline_vertical",
    "中心辐射": "hub_and_spoke",
    "中心发散": "hub_and_spoke",
    "辐射图": "hub_and_spoke",
    "左右分栏": "split_left_right",
    "左右分区": "split_left_right",
    "双栏": "split_left_right",
    "上下分区": "split_top_bottom",
    "上下分栏": "split_top_bottom",
    "标题正文": "split_top_bottom",
    "双轴对比": "compare_dual_axis",
    "双轴比较": "compare_dual_axis",
    "对比": "compare_dual_axis",
    "比较": "compare_dual_axis",
    "对照": "compare_dual_axis",
    "左右对照": "compare_dual_axis",
    "横向流程": "process_horizontal",
    "横向流程图": "process_horizontal",
    "流程图": "process_horizontal",
    "纵向流程": "process_vertical",
    "纵向流程图": "process_vertical",
    "封面主视觉": "hero_with_supporting_cards",
    "主视觉卡片": "hero_with_supporting_cards",
    "封面": "hero_with_supporting_cards",
    "大标题卡片": "hero_with_supporting_cards",
}

_LAYOUT_FAMILY_LIST = list(ALLOWED_LAYOUT_FAMILIES)


def normalize_layout_family_name(name: str) -> str:
    if not name:
        return "grid_n_x_m"
    cleaned = _normalize_layout_token(name)
    cleaned = _strip_number_suffix(cleaned)
    if validate_layout_family(cleaned):
        return cleaned
    for family, label in LAYOUT_FAMILY_LABELS.items():
        if _normalize_layout_token(label) == cleaned:
            return family
    if cleaned in _LAYOUT_ALIASES:
        return _LAYOUT_ALIASES[cleaned]
    for key, val in _LAYOUT_ALIASES.items():
        if key in cleaned or cleaned in key:
            return val
    return "grid_n_x_m"


def get_layout_family_label(name: str) -> str:
    family = normalize_layout_family_name(name)
    return LAYOUT_FAMILY_LABELS.get(family, family)


def build_layout_family_options(families: list[str] | None = None) -> list[dict[str, str]]:
    # 延迟导入避免版式画像与语法校验在模块初始化时形成循环依赖。
    from ppt_system.generation.layout_profiles import build_layout_profile_options

    return build_layout_profile_options(families)


def _build_legacy_layout_family_options(families: list[str] | None = None) -> list[dict[str, str]]:
    source = families if families is not None else DEFAULT_LAYOUT_FAMILIES
    options: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in source:
        family = normalize_layout_family_name(item)
        if family in seen:
            continue
        seen.add(family)
        options.append({"value": family, "label": get_layout_family_label(family)})
    return options


def format_layout_family_for_prompt(name: str) -> str:
    """将内部版式标识转换为面向中文模型提示词的名称。"""

    return get_layout_family_label(name)


def build_layout_family_prompt_catalog(families: list[str] | None = None) -> str:
    """生成规划模型可用的固定枚举目录，同时明确机器值与中文含义。"""

    return "；".join(
        f'"{item["value"]}"（{item["label"]}）'
        for item in build_layout_family_options(families)
    )


def _normalize_layout_token(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_").replace("-", "_")


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
    parts.append(
        f"版式家族：{'、'.join(format_layout_family_for_prompt(item) for item in style_guide.get('layout_families', []))}"
    )
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
        parts.append(f"版式家族：{'、'.join(format_layout_family_for_prompt(item) for item in families[:6])}")
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
    if layout_family_override:
        layout_family = format_layout_family_for_prompt(layout_family_override)
    else:
        layout_family = "、".join(
            format_layout_family_for_prompt(item)
            for item in style_guide.get("layout_families", [])[:3]
        )
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
