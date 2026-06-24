from __future__ import annotations

from typing import Any

from ppt_system.generation.design_grammar import compress_style_for_prompt, build_prompt_anchor
from ppt_system.generation.page_richness import build_page_richness_render_guidance, normalize_page_richness_level
from ppt_system.generation.prompt_visual_guidance import (
    build_no_reference_visual_guidance,
    build_reference_visual_consistency_guidance,
    build_template_quality_guidance,
    build_visual_requirement_line,
)
from ppt_system.generation.prompt_quality_rules import (
    enrich_reference_prompt_text,
    ensure_clean_rendering_line,
    strip_generated_prompt_clauses,
)
from ppt_system.generation.reference_shape_constraints import build_shape_clarity_prompt_lines
from ppt_system.generation.reference_style_adherence import (
    build_reference_style_adherence_prompt_lines,
    normalize_reference_style_adherence,
)


def build_reference_prompt_by_mode(
    page: dict[str, Any],
    style_notes: str,
    image_width: int,
    image_height: int,
    *,
    prompt_mode: str,
    style_guide: dict[str, Any] | None = None,
    has_reference_images: bool = False,
    reference_style_adherence: str = "balanced",
) -> str:
    normalized_mode = str(prompt_mode).strip().lower() or "baseline"
    if normalized_mode == "baseline":
        existing_prompt = str(page.get("image_prompt", "")).strip()
        if existing_prompt:
            return enrich_reference_prompt_text(existing_prompt)
        return build_reference_prompt(
            page,
            style_notes,
            image_width,
            image_height,
            style_guide=style_guide,
            has_reference_images=has_reference_images,
            reference_style_adherence=reference_style_adherence,
        )
    if normalized_mode == "compact":
        return build_compact_reference_prompt(
            page,
            style_notes,
            image_width,
            image_height,
            style_guide=style_guide,
            has_reference_images=has_reference_images,
            reference_style_adherence=reference_style_adherence,
        )
    if normalized_mode == "slot_brief":
        return build_slot_brief_reference_prompt(
            page,
            style_notes,
            image_width,
            image_height,
            style_guide=style_guide,
            has_reference_images=has_reference_images,
            reference_style_adherence=reference_style_adherence,
        )
    raise ValueError(f"未知的一阶段提示词模式：{prompt_mode}")


def build_reference_prompt(
    page: dict[str, Any],
    style_notes: str,
    image_width: int,
    image_height: int,
    style_guide: dict[str, Any] | None = None,
    has_reference_images: bool = False,
    reference_style_adherence: str = "balanced",
) -> str:
    style_guide = style_guide or {}
    title = str(page.get("title", f"第 {page.get('page_no', '')} 页"))
    summary = str(page.get("summary", ""))
    visual_suggestion = strip_generated_prompt_clauses(collect_visual_suggestion(page))
    texts = page.get("texts", [])
    layout_family = page.get("layout_family", "grid_n_x_m")
    raw_element_plan = page.get("element_plan", {})
    if isinstance(raw_element_plan, dict):
        element_plan = raw_element_plan.get("primitives", style_guide.get("element_primitives", []))
    elif isinstance(raw_element_plan, list):
        element_plan = raw_element_plan
    else:
        element_plan = style_guide.get("element_primitives", [])
    difference = page.get("difference_from_previous", "按本页内容重新生成具体构图")
    prompt_profile = page.get("prompt_profile", "compressed")

    text_lines: list[str] = []
    for item in texts:
        text_lines.append(
            f"- {item.get('role', 'text')}: {item.get('text', '')}，位置 x={item.get('left')} y={item.get('top')} w={item.get('width')} h={item.get('height')}"
        )

    style_section = compress_style_for_prompt(
        style_guide,
        mode=prompt_profile,
        layout_family_override=layout_family,
        difference_override=difference,
    )

    element_section = ""
    if element_plan:
        if isinstance(element_plan, list):
            element_section = f"元素语言要求：使用 {'、'.join(element_plan)}，按本页内容重新生成具体图形，不复用其他页的图形。"
        else:
            element_section = f"元素语言要求：{element_plan}"

    negative_rules = style_guide.get("negative_rules", [])
    negative_section = ""
    if negative_rules:
        negative_section = f"禁止事项：{'；'.join(negative_rules[:4])}"
    adherence_lines = build_reference_style_adherence_prompt_lines(
        reference_style_adherence,
        has_reference_images=has_reference_images,
    )

    prompt = "\n".join(
        [
            f"生成一张 {image_width}x{image_height}、16:9 的完整 PPT 单页效果图，必须包含文字。",
            style_section,
            f"页面标题：{title}",
            f"页面摘要：{summary}",
            f"本页视觉建议：{visual_suggestion}" if visual_suggestion else "",
            f"参考风格要求：{style_notes}",
            *adherence_lines,
            element_section,
            "文字要求：中文排版清晰，层级明确，标题和正文要可读；不要生成乱码。",
            build_visual_requirement_line(style_notes, style_guide),
            *build_shape_clarity_prompt_lines(style_guide, detail="full"),
            "布局要求：保持文字区和视觉元素区分明，元素之间留出足够间隔，方便后续识别和拆分。",
            negative_section,
            "建议文字布局：",
            *text_lines,
        ]
    )

    parts = [p for p in prompt.split("\n") if p.strip()]
    merged = "\n".join(parts)
    if len(merged) > 3000 and prompt_profile == "full":
        compressed_style = compress_style_for_prompt(
            style_guide,
            mode="compressed",
            layout_family_override=layout_family,
            difference_override=difference,
        )
        return enrich_reference_prompt_text("\n".join([
            f"生成一张 {image_width}x{image_height}、16:9 的完整 PPT 单页效果图，必须包含文字。",
            compressed_style,
            f"页面标题：{title}",
            f"页面摘要：{summary}",
            f"本页视觉建议：{visual_suggestion}" if visual_suggestion else "",
            *adherence_lines,
            element_section,
            negative_section,
            *text_lines,
        ]))
    return enrich_reference_prompt_text(merged)


def build_compact_reference_prompt(
    page: dict[str, Any],
    style_notes: str,
    image_width: int,
    image_height: int,
    *,
    style_guide: dict[str, Any] | None = None,
    has_reference_images: bool = False,
    reference_style_adherence: str = "balanced",
) -> str:
    style_guide = style_guide or {}
    title = str(page.get("title", f"第 {page.get('page_no', '')} 页")).strip()
    summary = str(page.get("summary", "")).strip()
    visual_suggestion = strip_generated_prompt_clauses(collect_visual_suggestion(page))
    layout_family = str(page.get("layout_family", "grid_n_x_m")).strip() or "grid_n_x_m"
    bullets = collect_page_bullets(page)
    slots = collect_page_slots(page)
    anchor = build_style_anchor(style_guide)
    page_richness = normalize_page_richness_level(page.get("page_richness", "medium"))
    adherence = normalize_reference_style_adherence(reference_style_adherence, "balanced")

    lines = [
        f"生成一张 {image_width}x{image_height}、16:9 的中文 PPT 单页效果图，文字必须清晰可读。",
    ]
    if has_reference_images:
        lines.extend(
            build_reference_style_adherence_prompt_lines(
                adherence,
                has_reference_images=has_reference_images,
            )
        )
        if adherence == "loose":
            lines.append("让新页面看起来明显属于同一套模板体系，但可以围绕内容重新安排模块重心。")
        elif adherence == "strict":
            lines.append("优先遵守原稿图的模板秩序与视觉密度，不要随意改写模块骨架。")
        else:
            lines.append("让新页面延续同一套模板体系，同时为本页内容保留适度变化空间。")
    else:
        lines.append(build_no_reference_visual_guidance(style_notes, style_guide, mode="compact"))
    lines.append(f"页面主题：{title}")
    if summary:
        lines.append(f"核心表达：{summary}")
    if visual_suggestion:
        lines.append(f"本页视觉建议：{visual_suggestion}")
    if bullets:
        lines.append("必须体现的要点：")
        lines.extend(f"- {bullet}" for bullet in select_prompt_bullets(bullets))
    if slots:
        lines.append(f"建议的信息分区：{'；'.join(slots[:4])}")
    if adherence == "strict" and has_reference_images:
        lines.append(f"组织方式请严格贴合 {layout_family} 的版式骨架，并优先沿用原稿图的模块秩序与卡片节奏。")
    elif adherence == "loose" and has_reference_images:
        lines.append(f"组织方式可参考 {layout_family}，但具体模块数量、箭头方向、图标组合和局部编排可由你围绕内容重新设计。")
    else:
        lines.append(f"组织方式可参考 {layout_family}，在统一框架下调整具体模块数量、箭头方向、图标组合和局部编排。")
    lines.append(f"内容丰富度要求：{build_page_richness_render_guidance(page_richness)}")
    if anchor:
        lines.append(f"统一视觉锚点：{anchor}")
    if style_notes:
        lines.append(f"补充风格说明：{style_notes}")
    lines.extend(build_shape_clarity_prompt_lines(style_guide, detail="compact"))
    lines = ensure_clean_rendering_line(lines)
    lines.append("不要乱码，不要堆满装饰，优先让信息关系清楚。")
    return "\n".join(lines)


def build_slot_brief_reference_prompt(
    page: dict[str, Any],
    style_notes: str,
    image_width: int,
    image_height: int,
    *,
    style_guide: dict[str, Any] | None = None,
    has_reference_images: bool = False,
    reference_style_adherence: str = "balanced",
) -> str:
    style_guide = style_guide or {}
    title = str(page.get("title", f"第 {page.get('page_no', '')} 页")).strip()
    summary = str(page.get("summary", "")).strip()
    visual_suggestion = strip_generated_prompt_clauses(collect_visual_suggestion(page))
    layout_family = str(page.get("layout_family", "grid_n_x_m")).strip() or "grid_n_x_m"
    bullets = collect_page_bullets(page)
    slots = collect_page_slots(page)
    anchor = build_style_anchor(style_guide)
    page_richness = normalize_page_richness_level(page.get("page_richness", "medium"))
    adherence = normalize_reference_style_adherence(reference_style_adherence, "balanced")

    lines = [
        f"请生成一张 {image_width}x{image_height}、16:9 的中文 PPT 单页效果图，文字清晰可读。",
    ]
    if has_reference_images:
        lines.extend(
            build_reference_style_adherence_prompt_lines(
                adherence,
                has_reference_images=has_reference_images,
            )
        )
    else:
        lines.append(build_no_reference_visual_guidance(style_notes, style_guide, mode="slot_brief"))
    lines.append(f"页面标题：{title}")
    if summary:
        lines.append(f"页面任务：{summary}")
    if visual_suggestion:
        lines.append(f"本页视觉建议：{visual_suggestion}")
    if bullets:
        lines.append("页面必须覆盖这些信息：")
        lines.extend(f"- {bullet}" for bullet in select_prompt_bullets(bullets))
    if slots:
        lines.append("请围绕以下语义分区组织页面，而不是机械照抄固定构图：")
        lines.extend(f"{index + 1}. {slot}" for index, slot in enumerate(slots[:5]))
    if adherence == "strict" and has_reference_images:
        lines.append(f"版式请严格贴近 {layout_family} 对应的原稿图骨架，卡片数量、层级关系和视觉节奏尽量与原稿图同源。")
        lines.append("优先按原稿图的模块组织方式安排视觉重心、流程方向、卡片分组和图标组合。")
    elif adherence == "loose" and has_reference_images:
        lines.append(f"版式只需大致接近 {layout_family}，无需强行复刻具体卡片数量或指定图标。")
        lines.append("你可以自主决定最适合的视觉重心、流程方向、卡片分组和图标组合。")
    else:
        lines.append(f"版式以 {layout_family} 为基准约束，保持框架统一，同时允许细节做适度调整。")
        lines.append("请在统一框架下决定视觉重心、流程方向、卡片分组和图标组合。")
    lines.append(f"内容丰富度要求：{build_page_richness_render_guidance(page_richness)}")
    if anchor:
        lines.append(f"统一视觉锚点：{anchor}")
    if style_notes:
        lines.append(f"补充风格说明：{style_notes}")
    lines.extend(build_shape_clarity_prompt_lines(style_guide, detail="compact"))
    lines = ensure_clean_rendering_line(lines)
    lines.append(build_template_quality_guidance(style_notes, style_guide))
    return "\n".join(lines)


def merge_prompt_with_style_lock(
    prompt: str,
    style_guide: dict[str, Any] | None = None,
    has_reference_images: bool = False,
    page: dict[str, Any] | None = None,
) -> str:
    style_guide = style_guide or {}
    page = page or {}

    prompt_anchor = str(style_guide.get("prompt_anchor", "")).strip()
    style_core = style_guide.get("style_core", {})
    layout_families = style_guide.get("layout_families", [])
    element_primitives = style_guide.get("element_primitives", [])
    negative_rules = style_guide.get("negative_rules", [])
    prompt_compression = str(style_guide.get("prompt_compression", "compressed")).strip()

    current_layout = page.get("layout_family", "")

    prefix: list[str] = []
    if has_reference_images:
        prefix.append(build_reference_visual_consistency_guidance())

    if prompt_anchor:
        prefix.append(f"统一风格锚点：{prompt_anchor}")

    if isinstance(style_core, dict) and style_core:
        core_items: list[str] = []
        for key in ["background_tone", "palette", "title_style", "card_style", "icon_style", "line_style"]:
            val = style_core.get(key, "")
            if isinstance(val, list):
                val = "、".join(val)
            if val:
                core_items.append(str(val))
        if core_items:
            prefix.append(f"风格固定层：{'，'.join(core_items)}")

    if layout_families and current_layout:
        prefix.append(f"版式家族：{'、'.join(layout_families[:6])}，本页骨架：{current_layout}")
    elif layout_families:
        prefix.append(f"版式家族：{'、'.join(layout_families[:6])}")

    prefix.append("继承风格，不继承具体构图。")
    prefix.append("继承元素语言，不复用具体图形。")

    if isinstance(style_core, dict):
        bg = style_core.get("background_tone", "")
        if bg:
            prefix.append(f"背景明度与底色要求：{bg}")
        palette_val = style_core.get("palette", [])
        if isinstance(palette_val, list) and palette_val:
            prefix.append(f"建议配色：{'、'.join(palette_val)}")

    must_keep = normalize_list(style_guide.get("must_keep", []))
    if must_keep:
        prefix.append(f"优先保持：{'；'.join(must_keep[:3])}")
    avoid = normalize_list(style_guide.get("avoid", []))
    if avoid:
        prefix.append(f"尽量避免：{'；'.join(avoid[:3])}")

    if negative_rules:
        prefix.append(f"禁止事项：{'；'.join(negative_rules[:4])}")

    result = "\n".join(prefix + [prompt]) if prefix else prompt

    if len(result) > 3000 and prompt_compression == "full":
        core_result = compress_style_for_prompt(style_guide, mode="core")
        return f"{core_result}\n{prompt}"
    if len(result) > 2500:
        compressed = compress_style_for_prompt(
            style_guide,
            mode="compressed",
            layout_family_override=current_layout,
        )
        return f"{compressed}\n{prompt}"

    return result


def build_elements_prompt(page: dict[str, Any] | None = None, style_guide: dict[str, Any] | None = None) -> str:
    page = page or {}
    style_guide = style_guide or {}

    element_primitives = style_guide.get("element_primitives", [])
    prompt_anchor = style_guide.get("prompt_anchor", "")
    anchor_desc = f"风格锚点：{prompt_anchor}。" if str(prompt_anchor).strip() else ""

    primitives_desc = ""
    if element_primitives:
        primitives_desc = f"保留以下元素类型：{'、'.join(element_primitives)}。"

    return (
        "将该图片中除了文字以外的所有元素生成1张背景为纯白色的图像"
        "（注意区分文字与logo/icon的区别，保留logo/icon，只去除文字），"
        "高对比度，高保真，没有任何阴影；保持所有元素的原始位置，"
        "不要移动或改变比例；不要有背景；画幅16：9。"
        f"{primitives_desc}"
        "仅删除文字，保留卡片/图标/箭头/编号/标签/容器。"
        "保持原有层级和相对位置。"
        "保留描边粗细和圆角风格。"
        "保留流程关系和反馈链路。"
        "不要重绘成另一套素材风格。"
        f"{anchor_desc}"
    )


def normalize_list(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [str(item).strip() for item in items if str(item).strip()]


def collect_page_bullets(page: dict[str, Any]) -> list[str]:
    bullets = page.get("bullets", [])
    if isinstance(bullets, list):
        cleaned = [str(item).strip() for item in bullets if str(item).strip()]
        if cleaned:
            return cleaned

    texts = page.get("texts", [])
    if not isinstance(texts, list):
        return []
    for item in texts:
        if str(item.get("role", "")).strip() != "body":
            continue
        lines = []
        for raw_line in str(item.get("text", "")).splitlines():
            line = raw_line.strip().lstrip("•").strip()
            if line:
                lines.append(line)
        if lines:
            return lines
    return []


def select_prompt_bullets(bullets: list[str], *, max_items: int = 8) -> list[str]:
    """选择送给生图模型的必要要点，避免固定截断造成核心模块丢失。"""

    cleaned = [str(item).strip() for item in bullets if str(item).strip()]
    if len(cleaned) <= max_items:
        return cleaned
    visible_count = max(1, max_items - 1)
    return [
        *cleaned[:visible_count],
        _compose_overflow_prompt_bullet(cleaned[visible_count:]),
    ]


def _compose_overflow_prompt_bullet(items: list[str]) -> str:
    headings = [_fact_heading(item) for item in items if str(item).strip()]
    if not headings:
        return "其他要点：按原文剩余事实归纳呈现。"
    return "其他要点：" + "；".join(headings)


def _fact_heading(text: str) -> str:
    cleaned = str(text or "").strip()
    for separator in ("：", ":"):
        if separator in cleaned:
            return cleaned.split(separator, 1)[0].strip()
    return cleaned[:40].rstrip()


def collect_page_slots(page: dict[str, Any]) -> list[str]:
    slots = page.get("layout_slots", [])
    if not isinstance(slots, list):
        return []
    return [str(slot).strip() for slot in slots if str(slot).strip()]


def collect_visual_suggestion(page: dict[str, Any]) -> str:
    return str(page.get("visual_suggestion") or page.get("style_constraints") or "").strip()


def build_style_anchor(style_guide: dict[str, Any] | None = None) -> str:
    style_guide = style_guide or {}
    prompt_anchor = str(style_guide.get("prompt_anchor", "")).strip()
    if prompt_anchor:
        return prompt_anchor

    style_core = style_guide.get("style_core", {})
    if not isinstance(style_core, dict):
        return ""
    return build_prompt_anchor({"style_core": style_core})
