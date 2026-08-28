from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from ppt_system.generation.design_grammar import (
    ALLOWED_LAYOUT_FAMILIES,
    DEFAULT_ELEMENT_PRIMITIVES,
    DEFAULT_LAYOUT_FAMILIES,
    DEFAULT_NEGATIVE_RULES,
    DEFAULT_STYLE_CORE,
    DEFAULT_VARIATION_POLICY,
    build_prompt_anchor,
    build_layout_family_prompt_catalog,
    compress_style_for_prompt,
    format_layout_family_for_prompt,
    normalize_design_grammar,
    normalize_layout_family_name,
    validate_layout_family,
)
from ppt_system.generation.generation_options import apply_page_count_constraints, default_generation_options
from ppt_system.generation.generation_prompts import build_reference_prompt_by_mode
from ppt_system.generation.generation_prompts import select_prompt_bullets
from ppt_system.integrations.openai_chat_provider import OpenAIChatProvider
from ppt_system.generation.planning_constraints import build_content_planning_constraints
from ppt_system.generation.page_richness import (
    DEFAULT_PAGE_RICHNESS,
    build_page_richness_prompt_lines,
    normalize_page_richness_level,
    resolve_page_richness_map,
)
from ppt_system.generation.layout_recommender import choose_layout_family, recommend_layout_candidates, recommend_layout_family
from ppt_system.generation.deck_layout_planner import build_deck_layout_report, plan_deck_layouts
from ppt_system.generation.planner import infer_style_type
from ppt_system.generation.reference_style_adherence import (
    build_reference_style_adherence_planning_guidance,
)
from ppt_system.generation.style_runtime import apply_text_theme
from ppt_system.generation.source_content_anchors import (
    build_source_content_anchors,
    format_source_anchors_for_prompt,
)
from ppt_system.generation.text_layout import build_layout_slots_by_family, build_text_boxes_from_slots, build_text_layouts
from ppt_system.generation.title_extraction import resolve_plan_title


def build_content_plan(
    provider: OpenAIChatProvider,
    content: str,
    page_count: int,
    image_width: int,
    image_height: int,
    style_notes: str,
    style_image_count: int,
    style_reference_paths: list[Path] | None = None,
    generation_options: dict[str, Any] | None = None,
    previous_plan: dict[str, Any] | None = None,
    evaluation_feedback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    style_reference_paths = style_reference_paths or []
    generation_options = {
        **default_generation_options(),
        **(generation_options or {}),
    }
    generation_options = apply_page_count_constraints(generation_options, page_count)
    page_richness_map = resolve_page_richness_map(
        page_count=page_count,
        default_level=str(generation_options.get("page_richness_default", DEFAULT_PAGE_RICHNESS)),
        explicit_map=generation_options.get("page_richness_map", {}),
    )
    generation_options["page_richness_map"] = page_richness_map
    reference_style_adherence = str(generation_options.get("reference_style_adherence", "balanced"))
    theme_color = str(generation_options.get("theme_color", "auto") or "auto").strip()
    prior_style_guide = previous_plan.get("style_guide") if isinstance(previous_plan, dict) else None
    style_guide = (
        copy.deepcopy(prior_style_guide)
        if isinstance(prior_style_guide, dict) and prior_style_guide
        else build_reference_style_guide(provider, style_reference_paths, style_notes)
    )
    if theme_color and theme_color != "auto":
        style_guide.setdefault("style_core", {})["user_theme_color"] = theme_color
    source_anchors = build_source_content_anchors(content, page_count)
    planning_prompt = build_planning_prompt(
        content=content,
        page_count=page_count,
        image_width=image_width,
        image_height=image_height,
        style_notes=style_notes,
        style_image_count=style_image_count,
        style_guide=style_guide,
        source_anchors=source_anchors,
        generation_options=generation_options,
        page_richness_map=page_richness_map,
    )
    if isinstance(previous_plan, dict) and isinstance(evaluation_feedback, dict):
        planning_prompt = build_planning_revision_prompt(planning_prompt, previous_plan, evaluation_feedback)
    messages = [
        {
            "role": "system",
            "content": (
                "你是专业 PPT 内容策划与图像提示词 agent。"
                "你必须只返回 JSON，不要返回 Markdown。"
                "你会把用户长文拆成指定页数的 PPT 页面结构，并为每页生成可直接用于 gpt-image-2 的中文生图提示词。"
                "页面事实只能来自用户输入内容，不得改写数字、分类、事项名称或业务结论。"
                "如果存在参考风格图，必须优先服从原稿图的版式语言、背景明度、主色、卡片结构与图标风格，"
                "内容变化不能破坏整套视觉一致性。"
            ),
        },
        {
            "role": "user",
            "content": planning_prompt,
        },
    ]
    result = provider.complete_json(messages, purpose="内容规划")
    normalized_plan = normalize_content_plan(
        result,
        content=content,
        page_count=page_count,
        image_width=image_width,
        image_height=image_height,
        style_notes=style_notes,
        style_guide=style_guide,
        has_reference_images=bool(style_reference_paths),
        generation_options=generation_options,
    )
    if isinstance(previous_plan, dict) and isinstance(evaluation_feedback, dict):
        return apply_planning_revision_guard(normalized_plan, previous_plan, evaluation_feedback)
    return normalized_plan


_PLANNING_REVISION_FIELDS_BY_CODE: dict[str, frozenset[str]] = {
    "invalid_layout_family": frozenset({
        "layout_family",
        "layout_reason",
        "layout_intent",
        "layout_slots",
        "layout_recommendation",
        "layout_candidates",
        "difference_from_previous",
    }),
    "layout_repeat": frozenset({
        "layout_family",
        "layout_reason",
        "layout_intent",
        "layout_slots",
        "layout_recommendation",
        "layout_candidates",
        "difference_from_previous",
    }),
}


def apply_planning_revision_guard(
    revised_plan: dict[str, Any],
    previous_plan: dict[str, Any],
    evaluation_feedback: dict[str, Any],
) -> dict[str, Any]:
    """按问题代码白名单合并修订，禁止模型借修订机会改写事实或无关字段。"""
    allowed_fields_by_page: dict[int, set[str]] = {}
    for finding in evaluation_feedback.get("findings", []):
        if not isinstance(finding, dict) or not finding.get("actionable", False):
            continue
        allowed_fields = _PLANNING_REVISION_FIELDS_BY_CODE.get(str(finding.get("code") or ""), frozenset())
        page_no = int(finding.get("page_no", 0) or 0)
        if page_no > 0 and allowed_fields:
            allowed_fields_by_page.setdefault(page_no, set()).update(allowed_fields)

    revised_pages = {
        int(page.get("page_no", 0) or 0): page
        for page in revised_plan.get("pages", [])
        if isinstance(page, dict)
    }
    guarded_plan = copy.deepcopy(previous_plan)
    guarded_pages: list[dict[str, Any]] = []
    for previous_page in previous_plan.get("pages", []):
        if not isinstance(previous_page, dict):
            continue
        page_no = int(previous_page.get("page_no", 0) or 0)
        guarded_page = copy.deepcopy(previous_page)
        revised_page = revised_pages.get(page_no)
        for field in allowed_fields_by_page.get(page_no, set()):
            if isinstance(revised_page, dict) and field in revised_page:
                guarded_page[field] = copy.deepcopy(revised_page[field])
        guarded_pages.append(guarded_page)

    guarded_plan["pages"] = guarded_pages
    return guarded_plan


def build_planning_revision_prompt(
    planning_prompt: str,
    previous_plan: dict[str, Any],
    evaluation_feedback: dict[str, Any],
) -> str:
    """构建带证据反馈的规划修订提示词，避免无反馈地整套重抽。"""
    actionable_findings = [
        finding
        for finding in evaluation_feedback.get("findings", [])
        if isinstance(finding, dict) and finding.get("actionable", False)
    ]
    feedback_payload = {
        "summary": evaluation_feedback.get("summary", ""),
        "findings": actionable_findings,
    }
    return (
        f"{planning_prompt}\n\n"
        "这是上一轮规划的质量修订，不是从零重新规划。必须以 previous_plan 为基础：\n"
        "- 只处理 evaluation_feedback.findings 中 actionable=true 的问题；未出现在反馈中的 warning 不得驱动任何修改。\n"
        "- 已通过且没有 actionable 问题的页面必须保持 title、summary、bullets、source_anchor_ids 和事实数字不变。\n"
        "- 修订版式或视觉提示词时，不得删除、扩写或改写用户事实；如需解决相邻版式重复，只调整相关页面的版式字段。\n"
        "- 每项修订必须能对应具体 finding 的 code、page_no 和 evidence；不得根据模糊评分自行重写。\n"
        "- 仍然返回完整且严格符合上述 JSON 契约的规划。\n\n"
        f"previous_plan：\n{json.dumps(previous_plan, ensure_ascii=False, indent=2)}\n\n"
        f"evaluation_feedback：\n{json.dumps(feedback_payload, ensure_ascii=False, indent=2)}"
    )


def build_reference_style_guide(
    provider: OpenAIChatProvider,
    style_reference_paths: list[Path],
    style_notes: str,
) -> dict[str, Any]:
    fallback = fallback_style_guide(style_notes, bool(style_reference_paths))
    if not style_reference_paths:
        return fallback

    content_items: list[dict[str, Any]] = [
        {
            "type": "input_text",
            "text": build_style_analysis_prompt(style_notes),
        }
    ]
    for path in style_reference_paths[:3]:
        content_items.append(provider.build_image_message_item(path))

    messages = [
        {
            "role": "system",
            "content": (
                "你是 PPT 视觉风格分析 agent。"
                "你只返回 JSON。"
                "你需要从原稿图片中提炼稳定的版式与视觉语言，"
                "供后续多页 PPT 统一复用。"
            ),
        },
        {
            "role": "user",
            "content": content_items,
        },
    ]
    try:
        result = provider.complete_json(messages, purpose="视觉风格分析")
    except Exception:
        return fallback
    return normalize_style_guide(result, fallback)


def build_style_analysis_prompt(style_notes: str) -> str:
    return f"""
请分析这些原稿图的 PPT 风格，只返回严格 JSON。

用户补充风格说明：
{style_notes or "无额外补充"}

JSON 格式必须如下：
{{
  "style_name": "一句话风格命名",
  "style_core": {{
    "background_tone": "背景明度与背景色特征",
    "palette": ["主色1", "主色2", "辅助色"],
    "title_style": "标题字体、颜色、大小特征",
    "card_style": "卡片描边、圆角、阴影特征",
    "icon_style": "图标风格特征",
    "line_style": "箭头、线条、连接器风格特征"
  }},
  "layout_families": ["原稿图对应的抽象排版模式1", "抽象排版模式2", "抽象排版模式3"],
  "element_primitives": ["元素原语1", "元素原语2", "元素原语3"],
  "variation_policy": {{
    "same_layout_max_repeat": 1,
    "min_distinct_layout_families": 3,
    "allow_local_recomposition": true
  }},
  "negative_rules": ["应避免的风格偏移1", "应避免的风格偏移2"],
  "prompt_anchor": "给后续生图用的一段统一风格锚点描述，1到2句话，概括整套 PPT 的视觉基调与关键信息图语言",
  "prompt_compression": "compressed"
}}

要求：
1. style_core 必须逐项提炼背景明度、配色、标题风格、卡片样式、图标风格、线条风格。
2. layout_families 只能从以下固定枚举中选择：{build_layout_family_prompt_catalog()}。字段值填写英文机器值，不得翻译、改写、组合或新增枚举；不能写成 layout_1、template_a 等模板编号。
3. element_primitives 从原稿图中提炼可复用的图形元素原语。
4. negative_rules 只总结与原稿图明显冲突的风格偏移，使用通用表达，不要写成过于具体的审美黑名单。
5. prompt_anchor 要适合直接拼接到每一页的生图提示词前面，避免过长、避免写成逐条硬性禁令。
6. layout_families 至少列出 3 种不同的抽象排版模式。
""".strip()


def fallback_style_guide(style_notes: str, has_reference_images: bool) -> dict[str, Any]:
    anchor = build_prompt_anchor({"style_core": DEFAULT_STYLE_CORE})
    if has_reference_images:
        return {
            "source": "fallback",
            "style_name": "原稿图优先统一风格",
            "style_core": {
                "background_tone": "优先继承原稿图的背景明度与主底色",
                "palette": ["继承原稿图主色", "继承原稿图辅助色"],
                "title_style": "继承原稿图标题字体与颜色",
                "card_style": "继承原稿图卡片描边与圆角",
                "icon_style": "继承原稿图图标风格",
                "line_style": "继承原稿图箭头与线条风格",
            },
            "layout_families": list(DEFAULT_LAYOUT_FAMILIES),
            "element_primitives": list(DEFAULT_ELEMENT_PRIMITIVES),
            "variation_policy": dict(DEFAULT_VARIATION_POLICY),
            "negative_rules": [
                "不要随意切换成另一种背景明度",
                "不要从信息图突然变成写实海报",
                "不要复用原稿图的具体构图",
            ],
            "constraint_sources": {
                "user": style_notes,
                "reference": "来自原稿图的视觉一致性约束",
                "system": "可读性与事实一致性基础规则",
            },
            "prompt_anchor": "优先延续原稿图的版式与视觉语言，保持背景明度、主色、卡片样式、图标与信息图结构的一致性。允许根据当前页内容调整局部编排，但整体气质不要跳出同一套风格。",
            "prompt_compression": "compressed",
        }

    return {
        "source": "fallback",
        "style_name": style_notes or "通用主题化简报",
        "style_core": dict(DEFAULT_STYLE_CORE),
        "layout_families": list(DEFAULT_LAYOUT_FAMILIES),
        "element_primitives": list(DEFAULT_ELEMENT_PRIMITIVES),
        "variation_policy": dict(DEFAULT_VARIATION_POLICY),
        "negative_rules": [],
        "constraint_sources": {
            "user": style_notes,
            "reference": "",
            "system": "可读性与事实一致性基础规则",
        },
        "prompt_anchor": anchor,
        "prompt_compression": "compressed",
    }


def normalize_style_guide(result: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    style_name = str(result.get("style_name") or fallback.get("style_name", "")).strip()
    source = str(result.get("source") or "vision").strip()

    raw_style_core = result.get("style_core")
    if isinstance(raw_style_core, dict):
        style_core = {}
        for key in ["background_tone", "palette", "title_style", "card_style", "icon_style", "line_style"]:
            val = raw_style_core.get(key)
            if val:
                style_core[key] = val
            else:
                default_core = fallback.get("style_core", DEFAULT_STYLE_CORE)
                style_core[key] = default_core.get(key, DEFAULT_STYLE_CORE.get(key, ""))
    else:
        style_core = dict(fallback.get("style_core", DEFAULT_STYLE_CORE))

    raw_families = result.get("layout_families")
    if isinstance(raw_families, list):
        families = []
        seen = set()
        for f in raw_families:
            fname = str(f).strip()
            if not fname:
                continue
            import re
            if re.match(r"^(layout|template)[_\s]?\w*\d*$", fname.lower()):
                continue
            norm = normalize_layout_family_name(fname)
            if norm not in seen:
                families.append(norm)
                seen.add(norm)
        if len(families) < 3:
            for df in DEFAULT_LAYOUT_FAMILIES:
                if df not in seen:
                    families.append(df)
                    seen.add(df)
                if len(families) >= 5:
                    break
    else:
        families = list(fallback.get("layout_families", DEFAULT_LAYOUT_FAMILIES))

    element_primitives = result.get("element_primitives")
    if isinstance(element_primitives, list) and element_primitives:
        element_primitives = [str(item).strip() for item in element_primitives if str(item).strip()]
    else:
        element_primitives = list(fallback.get("element_primitives", DEFAULT_ELEMENT_PRIMITIVES))

    raw_policy = result.get("variation_policy")
    if isinstance(raw_policy, dict):
        variation_policy = dict(DEFAULT_VARIATION_POLICY)
        variation_policy.update({k: v for k, v in raw_policy.items() if v is not None})
    else:
        variation_policy = dict(fallback.get("variation_policy", DEFAULT_VARIATION_POLICY))

    negative_rules = result.get("negative_rules")
    if isinstance(negative_rules, list) and negative_rules:
        negative_rules = [str(item).strip() for item in negative_rules if str(item).strip()]
    else:
        negative_rules = list(fallback.get("negative_rules", DEFAULT_NEGATIVE_RULES))

    prompt_anchor = str(result.get("prompt_anchor", "")).strip()
    if not prompt_anchor:
        prompt_anchor = str(fallback.get("prompt_anchor", "")).strip()
    if not prompt_anchor:
        prompt_anchor = build_prompt_anchor({"style_core": style_core})

    prompt_compression = str(result.get("prompt_compression", "")).strip()
    if not prompt_compression:
        prompt_compression = "compressed"

    return {
        "source": source,
        "style_name": style_name,
        "style_core": style_core,
        "layout_families": families,
        "element_primitives": element_primitives,
        "variation_policy": variation_policy,
        "negative_rules": negative_rules,
        "constraint_sources": {
            "user": str(fallback.get("constraint_sources", {}).get("user", "")),
            "reference": "来自原稿图分析的视觉偏移约束" if source == "vision" else "",
            "system": "可读性与事实一致性基础规则",
        },
        "prompt_anchor": prompt_anchor,
        "prompt_compression": prompt_compression,
    }


def build_planning_prompt(
    content: str,
    page_count: int,
    image_width: int,
    image_height: int,
    style_notes: str,
    style_image_count: int,
    style_guide: dict[str, Any],
    source_anchors: list[dict[str, Any]] | None = None,
    generation_options: dict[str, Any] | None = None,
    page_richness_map: dict[str, str] | None = None,
) -> str:
    generation_options = {
        **default_generation_options(),
        **(generation_options or {}),
    }
    generation_options = apply_page_count_constraints(generation_options, page_count)
    include_cover_page = bool(generation_options.get("include_cover_page", True))
    page_richness_map = page_richness_map or resolve_page_richness_map(
        page_count=page_count,
        default_level=str(generation_options.get("page_richness_default", DEFAULT_PAGE_RICHNESS)),
        explicit_map=generation_options.get("page_richness_map", {}),
    )
    reference_style_adherence = str(generation_options.get("reference_style_adherence", "balanced"))
    theme_color = str(generation_options.get("theme_color", "auto") or "auto").strip()
    resolved_prompt_mode = "slot_brief" if style_image_count > 0 else "compact"
    layout_families = style_guide.get("layout_families", [])
    layout_family_catalog = build_layout_family_prompt_catalog(layout_families)
    element_primitives = style_guide.get("element_primitives", [])
    source_anchors = source_anchors or build_source_content_anchors(content, page_count)
    style_direction = (
        style_notes.strip()
        if style_notes.strip()
        else "未指定固定风格，请你根据内容性质、主题和受众选择合适的视觉方向。"
    )
    cover_policy = (
        "第 1 页可以作为首页/封面页，但仍需承担明确表达职责。"
        if include_cover_page
        else "不生成纯封面；第 1 页直接进入正文核心观点、结构或要点。"
    )

    return f"""
请基于下面的 PPT 内容完成整套内容规划，拆成 {page_count} 页，并只输出严格 JSON。

输入内容：
{content}

可参考的源文定位锚点（辅助追溯，不要求机械分页）：
{format_source_anchors_for_prompt(source_anchors)}

风格方向：
{style_direction}

页面与生成参数：
- 目标页数：{page_count}
- 画幅：16:9，像素参考：{image_width}x{image_height}
- 首页策略：{cover_policy}
- 原稿图数量：{style_image_count}
- 原稿图约束：{build_reference_style_adherence_planning_guidance(reference_style_adherence, has_reference_images=style_image_count > 0)}
- 主题色偏好：{theme_color if theme_color and theme_color != "auto" else "未指定，请根据内容和参考图自动选择"}
- 后续原稿图阶段会使用 {resolved_prompt_mode} 模式统一生成最终生图提示词；这里的 image_prompt 只写本页独有视觉重点，可为空。

内容丰富度：
{chr(10).join(build_page_richness_prompt_lines(page_richness_map)) if page_richness_map else "- 所有页面使用中等丰富度"}

内容规划原则：
- 直接基于“输入内容”完成整套 PPT 规划；源文事实锚点只作为定位参考，不要机械按锚点顺序分页。
- 每页必须有明确且唯一的内容职责，title、summary、bullets 要讲同一个主题。
- 内容偏多时主动概括、合并和突出重点；内容偏少时只做与原文相关的轻量丰富，不新增无关事项、数字或结论。
- 不要无故删除输入中的关键要点；如果一页承载多个要点，可以合并表达或用“其他要点”概括剩余同类信息。
- source_anchor_ids 可填写本页参考到的锚点，供追溯使用；不能为了匹配锚点而牺牲你对页面主题和版式的整体判断。

版式与结构：
- layout_family 是封闭枚举，只能逐字填写以下英文机器值：{layout_family_catalog}
- 可用 element_primitives：{'、'.join(element_primitives)}
- 禁止自造、翻译、拼接或添加后缀，例如不得输出 layout_1、custom_layout、process_horizontal_2；没有完全匹配项时，从上述枚举中选择语义最接近的一项。
- 先判断本页信息关系，再选择最贴切的专用版式；优先使用能够直接表达语义的版式，例如转化用漏斗图、排期用甘特图、跨角色流程用泳道图、层级关系用组织架构或金字塔、指标分析用对应图表、根因分析用鱼骨图，不要把所有多要点页面都退化成宫格卡片。
- 每页先填写 layout_intent，说明本页是在表达对比、流程、时间、关系、数据、场景、总结还是行动计划；layout_family 必须服务于该意图。
- 同时考虑 page_richness：低密度优先主视觉、大数字、人物或产品展示；高密度优先仪表盘、数据表格、模块组合或清单；时间、流程、对比、循环等明确关系优先级高于密度偏好。
- layout_slots 必须与所选 layout_family 的结构一致，只写中文语义分区，不写坐标、英文槽位名或另一种版式的结构。

{build_content_planning_constraints(len(source_anchors), page_count)}

JSON 格式必须如下：
{{
  "style_type": "商务汇报/科技蓝图/视觉展示/通用简报等",
  "audience": "目标受众",
  "narrative": "整套 PPT 的叙事线",
  "pages": [
    {{
      "page_no": 1,
      "title": "页面标题，18字以内",
      "summary": "本页内容摘要",
      "bullets": ["要点1", "要点2", "要点3"],
      "layout_intent": {{"intent": "comparison/process/timeline/relationship/data_analysis/product_showcase/summary/action_plan/key_message", "content_role": "evidence/method/context/framework/example/closing/action/narrative", "density": "low/medium/high", "item_count": 3, "has_metrics": false, "has_process": false, "visual_priority": "low/medium/high"}},
      "source_anchor_ids": ["S01"],
      "layout_family": "grid_n_x_m",
      "layout_reason": "用中文完整说明为什么本页内容适合该版式，以及该版式如何组织信息。",
      "layout_slots": ["语义槽位1", "语义槽位2"],
      "element_plan": {{"primitives": ["本页使用的元素原语1", "元素原语2"], "icon_topics": ["图标主题1"], "diagram_type": "图表类型"}},
      "difference_from_previous": "与上一页的排版差异说明",
      "page_richness": "low/medium/high 之一",
      "style_constraints": "本页特别的风格约束",
      "reference_mode": "generation",
      "prompt_profile": "compressed",
      "image_prompt": "可选：1 到 3 句中文视觉重点说明，用来补充本页视觉侧重点，不是最终完整生图提示词。"
    }}
  ]
}}

要求：
1. pages 数量必须正好是 {page_count}。
2. 每页必须选择一个 layout_family，其值必须与上方封闭枚举中的某个英文机器值完全一致；禁止输出中文名、解释文字、模板编号或任何未列出的值。
3. layout_intent 必须与 title、summary、bullets 的实际内容一致，不能所有页面都填写同一种意图；item_count 与实际要点数量一致。
4. title、summary、bullets 必须忠于输入内容，不得自行计算、补写或改写数字口径。
4. page_richness 必须为 low、medium、high 之一，并与上面的丰富度要求一致。
5. reference_mode 只能填写 "generation" 或 "edit_with_refs"。
6. 文字会出现在第一阶段原稿图中，请保证标题和正文适合直接上屏。
7. 除 JSON 键名、上述固定枚举值和 reference_mode 外，所有面向人的文本字段必须使用中文，不得输出英文版式名称或中英混排说明。
""".strip()


def normalize_content_plan(
    result: dict[str, Any],
    content: str,
    page_count: int,
    image_width: int,
    image_height: int,
    style_notes: str,
    style_guide: dict[str, Any],
    has_reference_images: bool,
    generation_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generation_options = {
        **default_generation_options(),
        **(generation_options or {}),
    }
    generation_options = apply_page_count_constraints(generation_options, page_count)
    include_cover_page = bool(generation_options.get("include_cover_page", True))
    page_richness_map = resolve_page_richness_map(
        page_count=page_count,
        default_level=str(generation_options.get("page_richness_default", DEFAULT_PAGE_RICHNESS)),
        explicit_map=generation_options.get("page_richness_map", {}),
    )
    generation_options["page_richness_map"] = page_richness_map
    reference_style_adherence = str(generation_options.get("reference_style_adherence", "balanced"))
    resolved_prompt_mode = "slot_brief" if has_reference_images else "compact"
    source_anchors = build_source_content_anchors(content, page_count)
    fallback_pages = build_text_layouts(
        content,
        page_count=page_count,
        image_width=image_width,
        image_height=image_height,
    )
    style_type = str(result.get("style_type") or infer_style_type(content))
    pages_input = result.get("pages")
    if not isinstance(pages_input, list):
        pages_input = []

    style_families = style_guide.get("layout_families")
    available_families = list(DEFAULT_LAYOUT_FAMILIES)
    if isinstance(style_families, list):
        available_families = list(dict.fromkeys([*style_families, *available_families]))
    element_primitives = style_guide.get("element_primitives", list(DEFAULT_ELEMENT_PRIMITIVES))
    used_families: list[str] = []

    pages: list[dict[str, Any]] = []
    for index in range(page_count):
        fallback = fallback_pages[index]
        raw = pages_input[index] if index < len(pages_input) and isinstance(pages_input[index], dict) else {}
        page_richness = normalize_page_richness_level(
            raw.get("page_richness") or page_richness_map.get(str(index + 1)),
            page_richness_map.get(str(index + 1), DEFAULT_PAGE_RICHNESS),
        )
        raw_title = str(raw.get("title", "")).strip()
        raw_summary = str(raw.get("summary", "")).strip()
        bullets = _normalize_raw_bullets(raw.get("bullets"))
        title = str(raw_title or fallback["title"]).strip()
        summary = str(raw_summary or fallback["summary"]).strip()
        if bullets:
            fallback["texts"][1]["text"] = _format_body_bullets(bullets)

        layout_candidates = recommend_layout_candidates(
            title,
            summary,
            bullets,
            page_richness=page_richness,
            candidate_families=available_families,
            page_index=index,
            include_cover_page=include_cover_page,
        )
        inferred_intent = layout_candidates[0].get("layout_intent", {}) if layout_candidates else {}
        raw_intent = raw.get("layout_intent")
        layout_intent = raw_intent if isinstance(raw_intent, dict) else inferred_intent
        layout_reason = str(raw.get("layout_reason") or "").strip()
        requested_family = normalize_layout_family_name(str(raw.get("layout_family", "")).strip())
        requested_is_recommended = any(item["value"] == requested_family for item in layout_candidates)
        requested_is_confirmed = bool(raw.get("layout_locked") or raw.get("layout_user_confirmed") or raw.get("layout_source") == "user")
        if validate_layout_family(requested_family) and (requested_is_recommended or requested_is_confirmed):
            layout_family = requested_family
        else:
            layout_family = choose_layout_family(
                requested_family,
                title,
                summary,
                bullets,
                page_richness=page_richness,
                candidate_families=available_families,
                # 单页没有跨页上下文，不参与相邻去重或整套编排。
                previous_family=used_families[-1] if page_count > 1 and used_families else "",
                page_index=index,
                include_cover_page=include_cover_page,
            )
        # 用户确认的版式必须保持不变，不能被相邻去重策略覆盖。
        if page_count > 1 and not requested_family and index > 0 and len(used_families) > 0 and layout_family == used_families[-1]:
            alternatives = [candidate for candidate in available_families if candidate != used_families[-1]]
            layout_family = recommend_layout_family(
                title,
                summary,
                bullets,
                page_richness=page_richness,
                candidate_families=alternatives,
                previous_family=used_families[-1],
                page_index=index,
                include_cover_page=include_cover_page,
            )
        # 用已选页面作为上下文进行贪心编排，避免相邻页面结构重复。
        if page_count > 1 and used_families and not requested_family:
            previous_candidate = [{"value": used_families[-1], "score": 0, "reason": {}}]
            planned = plan_deck_layouts([previous_candidate, layout_candidates], locked_families=[None, None])
            if len(planned) == 2 and planned[1]:
                layout_family = planned[1]["value"]
        used_families.append(layout_family)

        layout_slots = raw.get("layout_slots", [])
        if not isinstance(layout_slots, list):
            layout_slots = _default_layout_slots(layout_family, title, bullets)

        raw_element_plan = raw.get("element_plan", {})
        if isinstance(raw_element_plan, list):
            element_plan = {"primitives": raw_element_plan, "icon_topics": [], "diagram_type": "default"}
        elif isinstance(raw_element_plan, dict):
            primitives = raw_element_plan.get("primitives", [])
            if not isinstance(primitives, list) or not primitives:
                primitives = list(element_primitives)
            element_plan = {
                "primitives": primitives,
                "icon_topics": raw_element_plan.get("icon_topics", []),
                "diagram_type": raw_element_plan.get("diagram_type", "default"),
            }
        else:
            element_plan = {"primitives": list(element_primitives), "icon_topics": [], "diagram_type": "default"}

        difference_from_previous = str(raw.get("difference_from_previous", "")).strip()
        if not difference_from_previous:
            if index == 0:
                difference_from_previous = "首页建立视觉基调" if include_cover_page else "正文开篇，直接进入核心内容"
            else:
                prev_family = used_families[-2] if len(used_families) >= 2 else ""
                difference_from_previous = (
                    f"从{format_layout_family_for_prompt(prev_family)}切换到"
                    f"{format_layout_family_for_prompt(layout_family)}，重新生成具体构图"
                )

        style_constraints = str(raw.get("style_constraints", "")).strip() if has_reference_images else ""
        reference_mode = "edit_with_refs" if has_reference_images else "generation"
        prompt_profile = str(raw.get("prompt_profile", "compressed")).strip()

        texts = fallback.get("texts", [])
        fallback_family = fallback.get("layout_family", "split_left_right")
        body = _format_body_bullets(bullets) if bullets else summary
        if layout_family != fallback_family:
            body_sentences = summary.split() if summary else []
            body = "\n".join(f"• {item}" for item in body_sentences[:5])
            if bullets:
                body = _format_body_bullets(bullets)
            slots = build_layout_slots_by_family(layout_family, image_width, image_height, page_richness)
            rebuilt_texts = build_text_boxes_from_slots(slots, title, body, image_width, image_height)
            if rebuilt_texts and len(rebuilt_texts) > 1:
                texts = rebuilt_texts
        texts = _sync_text_boxes_with_page_content(texts, title, body)
        texts = apply_text_theme(texts, style_guide)

        planner_image_prompt = str(raw.get("image_prompt", "")).strip()
        page = {
            "page_no": index + 1,
            "title": title,
            "summary": summary,
            "bullets": bullets,
            "layout_intent": layout_intent,
            "layout_family": layout_family,
            "layout_candidates": layout_candidates,
            "layout_recommendation": {
                **(next((item for item in layout_candidates if item["value"] == layout_family), layout_candidates[0] if layout_candidates else {})),
                "ai_reason": layout_reason,
            },
            "layout_reason": layout_reason,
            "layout_locked": bool(raw.get("layout_locked")),
            "layout_user_confirmed": bool(raw.get("layout_user_confirmed")),
            "layout_source": str(raw.get("layout_source") or "ai"),
            "layout_slots": layout_slots,
            "element_plan": element_plan,
            "difference_from_previous": difference_from_previous,
            "page_richness": page_richness,
            "style_constraints": style_constraints,
            "visual_suggestion": str(raw.get("visual_suggestion", "")).strip(),
            "reference_mode": reference_mode,
            "prompt_profile": prompt_profile,
            "reference_style_adherence": reference_style_adherence,
            "source_anchor_ids": _normalize_source_anchor_ids(raw.get("source_anchor_ids"), source_anchors),
            "texts": texts,
        }
        page["planner_image_prompt"] = planner_image_prompt
        if planner_image_prompt:
            page["image_prompt"] = planner_image_prompt
        page["image_prompt"] = build_reference_prompt_by_mode(
            page,
            style_notes,
            image_width,
            image_height,
            prompt_mode=resolved_prompt_mode,
            style_guide=style_guide,
            has_reference_images=has_reference_images,
            reference_style_adherence=reference_style_adherence,
        )
        pages.append(page)

    layout_report = build_deck_layout_report(
        [{"value": page["layout_family"]} for page in pages]
    )
    for page in pages:
        page["layout_report"] = layout_report

    return {
        "title": resolve_plan_title(result.get("title"), fallback_content=content),
        "style_type": style_type,
        "audience": str(result.get("audience", "")).strip(),
        "narrative": str(result.get("narrative", "")).strip(),
        "page_count": page_count,
        "generation_options": generation_options,
        "style_guide": style_guide,
        "pages": pages,
        "layout_report": layout_report,
    }


def _normalize_raw_bullets(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_source_anchor_ids(value: Any, source_anchors: list[dict[str, Any]]) -> list[str]:
    if isinstance(value, str):
        candidates = [value.strip()] if value.strip() else []
    elif isinstance(value, list):
        candidates = [str(item).strip() for item in value if str(item).strip()]
    else:
        return []

    available_ids = {str(anchor.get("id", "")).strip() for anchor in source_anchors if anchor.get("id")}
    if not available_ids:
        return candidates
    return [item for item in candidates if item in available_ids]


def _sync_text_boxes_with_page_content(texts: list[dict[str, Any]], title: str, body: str) -> list[dict[str, Any]]:
    synced: list[dict[str, Any]] = []
    body_applied = False
    for item in texts:
        if not isinstance(item, dict):
            continue
        next_item = dict(item)
        role = str(next_item.get("role", "")).strip().lower()
        if role == "title":
            next_item["text"] = title
        elif role == "body" and not body_applied:
            next_item["text"] = body
            body_applied = True
        synced.append(next_item)
    return synced or texts


def _format_body_bullets(bullets: list[str]) -> str:
    return "\n".join(f"• {item}" for item in select_prompt_bullets(bullets))


def _default_layout_slots(layout_family: str, title: str, bullets: list[str]) -> list[str]:
    if layout_family in ("grid_n_x_m",):
        return ["标题区"] + [f"卡片区{i+1}" for i in range(min(len(bullets), 4))]
    if layout_family in ("timeline_horizontal", "timeline_vertical"):
        return ["标题区", "时间轴", "节点1", "节点2", "节点3"]
    if layout_family in ("process_horizontal", "process_vertical"):
        return ["标题区", "步骤1", "步骤2", "步骤3"]
    if layout_family in ("hub_and_spoke",):
        return ["中心主题", "分支1", "分支2", "分支3", "分支4"]
    if layout_family in ("split_left_right",):
        return ["左侧内容区", "右侧内容区"]
    if layout_family in ("split_top_bottom",):
        return ["上方内容区", "下方内容区"]
    if layout_family in ("compare_dual_axis",):
        return ["标题区", "左侧对比项", "右侧对比项", "对比维度"]
    if layout_family in ("hero_with_supporting_cards",):
        return ["主视觉区", "辅助卡片1", "辅助卡片2", "辅助卡片3"]
    if validate_layout_family(layout_family):
        return ["标题区", f"{format_layout_family_for_prompt(layout_family)}主体区"]
    return ["标题区", "内容区"]
