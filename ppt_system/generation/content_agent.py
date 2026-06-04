from __future__ import annotations

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
    compress_style_for_prompt,
    normalize_design_grammar,
    normalize_layout_family_name,
    validate_layout_family,
)
from ppt_system.generation.generation_options import default_generation_options
from ppt_system.generation.generation_prompts import build_reference_prompt_by_mode
from ppt_system.integrations.openai_chat_provider import OpenAIChatProvider
from ppt_system.generation.page_richness import (
    DEFAULT_PAGE_RICHNESS,
    build_page_richness_planning_guidance,
    build_page_richness_prompt_lines,
    normalize_page_richness_level,
    resolve_page_richness_map,
)
from ppt_system.generation.planner import infer_style_type
from ppt_system.generation.reference_style_adherence import (
    build_reference_style_adherence_planning_guidance,
    get_reference_style_adherence_label,
)
from ppt_system.generation.style_runtime import apply_text_theme
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
) -> dict[str, Any]:
    style_reference_paths = style_reference_paths or []
    generation_options = {
        **default_generation_options(),
        **(generation_options or {}),
    }
    page_richness_map = resolve_page_richness_map(
        page_count=page_count,
        default_level=str(generation_options.get("page_richness_default", DEFAULT_PAGE_RICHNESS)),
        explicit_map=generation_options.get("page_richness_map", {}),
    )
    generation_options["page_richness_map"] = page_richness_map
    reference_style_adherence = str(generation_options.get("reference_style_adherence", "balanced"))
    style_guide = build_reference_style_guide(provider, style_reference_paths, style_notes)
    messages = [
        {
            "role": "system",
            "content": (
                "你是专业 PPT 内容策划与图像提示词 agent。"
                "你必须只返回 JSON，不要返回 Markdown。"
                "你会把用户长文拆成指定页数的 PPT 页面结构，并为每页生成可直接用于 gpt-image-2 的中文生图提示词。"
                "如果存在参考风格图，必须优先服从原稿图的版式语言、背景明度、主色、卡片结构与图标风格，"
                "内容变化不能破坏整套视觉一致性。"
            ),
        },
        {
            "role": "user",
            "content": build_planning_prompt(
                content=content,
                page_count=page_count,
                image_width=image_width,
                image_height=image_height,
                style_notes=style_notes,
                style_image_count=style_image_count,
                style_guide=style_guide,
                generation_options=generation_options,
                page_richness_map=page_richness_map,
            ),
        },
    ]
    result = provider.complete_json(messages)
    return normalize_content_plan(
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
            "type": "text",
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
        result = provider.complete_json(messages)
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
2. layout_families 必须是抽象排版模式名称（如 grid_n_x_m、timeline_horizontal），不能写成编号式模板名（如 layout_1、template_a）。
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
        "negative_rules": list(DEFAULT_NEGATIVE_RULES),
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
    generation_options: dict[str, Any] | None = None,
    page_richness_map: dict[str, str] | None = None,
) -> str:
    generation_options = {
        **default_generation_options(),
        **(generation_options or {}),
    }
    include_cover_page = bool(generation_options.get("include_cover_page", True))
    page_richness_map = page_richness_map or resolve_page_richness_map(
        page_count=page_count,
        default_level=str(generation_options.get("page_richness_default", DEFAULT_PAGE_RICHNESS)),
        explicit_map=generation_options.get("page_richness_map", {}),
    )
    reference_style_adherence = str(generation_options.get("reference_style_adherence", "balanced"))
    reference_style_adherence_label = get_reference_style_adherence_label(reference_style_adherence)
    resolved_prompt_mode = "slot_brief" if style_image_count > 0 else "compact"
    prompt_anchor = style_guide.get("prompt_anchor", "")
    style_core = style_guide.get("style_core", {})
    layout_families = style_guide.get("layout_families", [])
    element_primitives = style_guide.get("element_primitives", [])
    variation_policy = style_guide.get("variation_policy", {})
    negative_rules = style_guide.get("negative_rules", [])

    core_lines: list[str] = []
    if isinstance(style_core, dict):
        for key in ["background_tone", "palette", "title_style", "card_style", "icon_style", "line_style"]:
            val = style_core.get(key, "")
            if isinstance(val, list):
                val = "、".join(val)
            if val:
                core_lines.append(f"- {key}：{val}")

    return f"""
请根据下面的 PPT 内容，拆成 {page_count} 页，并输出严格 JSON。

输入内容：
{content}

参考风格补充：
{style_notes or "用户没有填写风格补充，请根据内容自行判断。"}

参考风格图片数量：{style_image_count}
原稿图约束强度：{reference_style_adherence_label}
画幅：16:9
像素参考：{image_width}x{image_height}
首页图策略：{"第 1 页允许作为 PPT 首页图/封面页，用于建立视觉基调" if include_cover_page else "不生成单独首页图；第 1 页必须直接进入正文内容"}
第一阶段提示策略：系统会在原稿图生成阶段使用 {resolved_prompt_mode} 模式统一生成最终生图提示词；这里不要求你为每页写成长篇最终 prompt。

统一风格锚点：
{prompt_anchor}

风格核心：
{chr(10).join(core_lines) if core_lines else "使用默认风格"}

可用版式家族：
{'、'.join(layout_families)}

元素原语：
{'、'.join(element_primitives)}

变化策略：
- 相邻页不能重复同一 layout_family
- 整套页至少覆盖 {variation_policy.get('min_distinct_layout_families', 3)} 种以上骨架
- 同一 layout_family 最多连续重复 {variation_policy.get('same_layout_max_repeat', 1)} 次

每页内容丰富度要求：
{chr(10).join(build_page_richness_prompt_lines(page_richness_map)) if page_richness_map else "- 所有页面使用中等丰富度"}

禁止事项：
{format_style_list(negative_rules)}

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
      "layout_family": "从可用版式家族中选择一个抽象排版模式",
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
2. 每页必须选择一个 layout_family，必须从可用版式家族中选择，不能写成模板编号。
3. 相邻页不能重复同一 layout_family。
4. 整套页至少覆盖 3 种以上不同的 layout_family。
5. 必须继承 element_primitives，每页按本页内容重新生成具体图形。
6. 不允许复用原稿图的具体构图，每页必须有 difference_from_previous。
7. layout_slots 是语义槽位，描述本页信息分区的含义，不是固定像素坐标。
8. image_prompt 可以为空；如果填写，也只写本页独有的视觉重点，避免重复整套固定风格。
9. 文字要出现在图中，因为这是第一阶段带文字原稿图。
10. logo/icon 属于视觉元素，不要把它们描述成要删除的文字。
11. 如果存在参考风格图，页面结构需要保持统一风格锚点，但允许为了表达本页内容调整局部构图与信息模块。
12. {build_reference_style_adherence_planning_guidance(reference_style_adherence, has_reference_images=style_image_count > 0)}
13. reference_mode 只能填写 "generation" 或 "edit_with_refs"。
14. page_richness 必须填写为 low、medium、high 之一，并与该页丰富度要求保持一致。
15. {"如果第 1 页作为首页图，内容应承担封面/总题页职责，同时仍需与全套风格一致。" if include_cover_page else "不要生成只有标题、日期、Logo 或一句口号的封面页；第 1 页必须直接呈现正文核心观点、结构或要点。"}
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
    include_cover_page = bool(generation_options.get("include_cover_page", True))
    page_richness_map = resolve_page_richness_map(
        page_count=page_count,
        default_level=str(generation_options.get("page_richness_default", DEFAULT_PAGE_RICHNESS)),
        explicit_map=generation_options.get("page_richness_map", {}),
    )
    generation_options["page_richness_map"] = page_richness_map
    reference_style_adherence = str(generation_options.get("reference_style_adherence", "balanced"))
    resolved_prompt_mode = "slot_brief" if has_reference_images else "compact"
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

    available_families = style_guide.get("layout_families", list(DEFAULT_LAYOUT_FAMILIES))
    element_primitives = style_guide.get("element_primitives", list(DEFAULT_ELEMENT_PRIMITIVES))
    used_families: list[str] = []

    pages: list[dict[str, Any]] = []
    for index in range(page_count):
        fallback = fallback_pages[index]
        raw = pages_input[index] if index < len(pages_input) and isinstance(pages_input[index], dict) else {}
        bullets = raw.get("bullets", [])
        if not isinstance(bullets, list):
            bullets = []
        bullets = [str(item).strip() for item in bullets if str(item).strip()]
        title = str(raw.get("title") or fallback["title"]).strip()
        summary = str(raw.get("summary") or fallback["summary"]).strip()
        if bullets:
            fallback["texts"][1]["text"] = "\n".join(f"• {item}" for item in bullets[:5])

        layout_family = str(raw.get("layout_family", "")).strip()
        if not layout_family:
            layout_family = _infer_layout_family(title, summary, bullets, index)
        else:
            layout_family = normalize_layout_family_name(layout_family)
            if not validate_layout_family(layout_family):
                layout_family = _infer_layout_family(title, summary, bullets, index)
        if index > 0 and len(used_families) > 0 and layout_family == used_families[-1]:
            for candidate in available_families:
                if candidate != used_families[-1]:
                    layout_family = candidate
                    break
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
                difference_from_previous = f"从 {prev_family} 切换到 {layout_family}，重新生成具体构图"

        style_constraints = str(raw.get("style_constraints", "")).strip()
        reference_mode = "edit_with_refs" if has_reference_images else "generation"
        prompt_profile = str(raw.get("prompt_profile", "compressed")).strip()
        page_richness = normalize_page_richness_level(
            raw.get("page_richness") or page_richness_map.get(str(index + 1)),
            page_richness_map.get(str(index + 1), DEFAULT_PAGE_RICHNESS),
        )
        richness_guidance = build_page_richness_planning_guidance(page_richness)
        if style_constraints:
            style_constraints = f"{style_constraints}；内容丰富度要求：{richness_guidance}"
        else:
            style_constraints = f"内容丰富度要求：{richness_guidance}"

        texts = fallback.get("texts", [])
        fallback_family = fallback.get("layout_family", "split_left_right")
        if layout_family != fallback_family:
            body_sentences = summary.split() if summary else []
            body = "\n".join(f"• {item}" for item in body_sentences[:5])
            if bullets:
                body = "\n".join(f"• {item}" for item in bullets[:5])
            slots = build_layout_slots_by_family(layout_family, image_width, image_height)
            rebuilt_texts = build_text_boxes_from_slots(slots, title, body, image_width, image_height)
            if rebuilt_texts and len(rebuilt_texts) > 1:
                texts = rebuilt_texts
        texts = apply_text_theme(texts, style_guide)

        page = {
            "page_no": index + 1,
            "title": title,
            "summary": summary,
            "bullets": bullets,
            "layout_intent": str(raw.get("layout_intent", "")).strip(),
            "layout_family": layout_family,
            "layout_slots": layout_slots,
            "element_plan": element_plan,
            "difference_from_previous": difference_from_previous,
            "page_richness": page_richness,
            "style_constraints": style_constraints,
            "reference_mode": reference_mode,
            "prompt_profile": prompt_profile,
            "reference_style_adherence": reference_style_adherence,
            "texts": texts,
        }
        planner_image_prompt = str(raw.get("image_prompt", "")).strip()
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

    return {
        "title": resolve_plan_title(result.get("title"), fallback_content=content),
        "style_type": style_type,
        "audience": str(result.get("audience", "")).strip(),
        "narrative": str(result.get("narrative", "")).strip(),
        "page_count": page_count,
        "generation_options": generation_options,
        "style_guide": style_guide,
        "pages": pages,
    }


_CONTENT_FAMILY_MAP: list[tuple[list[str], str]] = [
    (["趋势", "时间", "发展", "历史", "演变", "阶段"], "timeline_horizontal"),
    (["对比", "比较", "竞争", "对手", "优劣"], "compare_dual_axis"),
    (["流程", "步骤", "阶段", "执行", "落地"], "process_horizontal"),
    (["架构", "模块", "组件", "系统", "中心"], "hub_and_spoke"),
    (["核心", "要点", "重点", "亮点"], "hero_with_supporting_cards"),
    (["左右", "平衡", "两端", "两侧"], "split_left_right"),
    (["上下", "层级", "分层", "垂直"], "split_top_bottom"),
    (["网格", "并列", "罗列", "清单", "多维"], "grid_n_x_m"),
]


def _infer_layout_family(title: str, summary: str, bullets: list[str], index: int) -> str:
    combined = f"{title} {summary} {' '.join(bullets)}"
    for keywords, family in _CONTENT_FAMILY_MAP:
        for kw in keywords:
            if kw in combined:
                return family
    rotation = DEFAULT_LAYOUT_FAMILIES[index % len(DEFAULT_LAYOUT_FAMILIES)]
    return rotation


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
    return ["标题区", "内容区"]


def format_style_list(items: list[Any]) -> str:
    cleaned = [str(item).strip() for item in items if str(item).strip()]
    if not cleaned:
        return "无"
    return "；".join(cleaned)
