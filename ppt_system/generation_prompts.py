from __future__ import annotations

from typing import Any

from ppt_system.design_grammar import compress_style_for_prompt, build_prompt_anchor


def build_reference_prompt_by_mode(
    page: dict[str, Any],
    style_notes: str,
    image_width: int,
    image_height: int,
    *,
    prompt_mode: str,
    style_guide: dict[str, Any] | None = None,
    has_reference_images: bool = False,
) -> str:
    normalized_mode = str(prompt_mode).strip().lower() or "baseline"
    if normalized_mode == "baseline":
        existing_prompt = str(page.get("image_prompt", "")).strip()
        if existing_prompt:
            return existing_prompt
        return build_reference_prompt(
            page,
            style_notes,
            image_width,
            image_height,
            style_guide=style_guide,
            has_reference_images=has_reference_images,
        )
    if normalized_mode == "compact":
        return build_compact_reference_prompt(
            page,
            style_notes,
            image_width,
            image_height,
            style_guide=style_guide,
            has_reference_images=has_reference_images,
        )
    if normalized_mode == "slot_brief":
        return build_slot_brief_reference_prompt(
            page,
            style_notes,
            image_width,
            image_height,
            style_guide=style_guide,
            has_reference_images=has_reference_images,
        )
    raise ValueError(f"未知的一阶段提示词模式：{prompt_mode}")


def build_reference_prompt(
    page: dict[str, Any],
    style_notes: str,
    image_width: int,
    image_height: int,
    style_guide: dict[str, Any] | None = None,
    has_reference_images: bool = False,
) -> str:
    style_guide = style_guide or {}
    title = str(page.get("title", f"第 {page.get('page_no', '')} 页"))
    summary = str(page.get("summary", ""))
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

    prompt = "\n".join(
        [
            f"生成一张 {image_width}x{image_height}、16:9 的完整 PPT 单页效果图，必须包含文字。",
            style_section,
            f"页面标题：{title}",
            f"页面摘要：{summary}",
            f"参考风格要求：{style_notes}",
            element_section,
            "文字要求：中文排版清晰，层级明确，标题和正文要可读；不要生成乱码。",
            "视觉要求：边界清晰，高级商务科技风格，元素低透明但轮廓明确，图标/logo/icon 可以保留。",
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
        return "\n".join([
            f"生成一张 {image_width}x{image_height}、16:9 的完整 PPT 单页效果图，必须包含文字。",
            compressed_style,
            f"页面标题：{title}",
            f"页面摘要：{summary}",
            element_section,
            negative_section,
            *text_lines,
        ])
    return merged


def build_compact_reference_prompt(
    page: dict[str, Any],
    style_notes: str,
    image_width: int,
    image_height: int,
    *,
    style_guide: dict[str, Any] | None = None,
    has_reference_images: bool = False,
) -> str:
    style_guide = style_guide or {}
    title = str(page.get("title", f"第 {page.get('page_no', '')} 页")).strip()
    summary = str(page.get("summary", "")).strip()
    layout_family = str(page.get("layout_family", "grid_n_x_m")).strip() or "grid_n_x_m"
    bullets = collect_page_bullets(page)
    slots = collect_page_slots(page)
    anchor = build_style_anchor(style_guide)

    lines = [
        f"生成一张 {image_width}x{image_height}、16:9 的中文 PPT 单页效果图，文字必须清晰可读。",
    ]
    if has_reference_images:
        lines.append(
            "如果提供了参考图，请把它们当成同一套 PPT 的视觉母版：优先继承背景明度、留白比例、描边粗细、圆角、卡片密度、图标语言和配色比例。"
        )
        lines.append("不要复制任一参考图的具体构图，但要让新页面看起来明显属于同一套模板体系。")
    else:
        lines.append("整体保持高级企业汇报 / 咨询信息图气质，结构清晰、边界明确、留白充足。")
    lines.append(f"页面主题：{title}")
    if summary:
        lines.append(f"核心表达：{summary}")
    if bullets:
        lines.append("必须体现的要点：")
        lines.extend(f"- {bullet}" for bullet in bullets[:5])
    if slots:
        lines.append(f"建议的信息分区：{'；'.join(slots[:4])}")
    lines.append(f"组织方式可参考 {layout_family}，但具体模块数量、箭头方向、图标组合和局部编排由你自主决定。")
    if anchor:
        lines.append(f"统一视觉锚点：{anchor}")
    if style_notes:
        lines.append(f"补充风格说明：{style_notes}")
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
) -> str:
    style_guide = style_guide or {}
    title = str(page.get("title", f"第 {page.get('page_no', '')} 页")).strip()
    summary = str(page.get("summary", "")).strip()
    layout_family = str(page.get("layout_family", "grid_n_x_m")).strip() or "grid_n_x_m"
    bullets = collect_page_bullets(page)
    slots = collect_page_slots(page)
    anchor = build_style_anchor(style_guide)

    lines = [
        f"请生成一张 {image_width}x{image_height}、16:9 的中文 PPT 单页效果图，文字清晰可读。",
    ]
    if has_reference_images:
        lines.append("优先学习参考图的版芯比例、留白、背景纹理、线条样式、卡片层级和色彩节奏，再围绕本页内容重新设计。")
        lines.append("不要照搬某一张参考图的具体版式，只需要保持同系列视觉一致性。")
    else:
        lines.append("围绕本页内容重新组织页面，保持咨询信息图式的理性与秩序。")
    lines.append(f"页面标题：{title}")
    if summary:
        lines.append(f"页面任务：{summary}")
    if bullets:
        lines.append("页面必须覆盖这些信息：")
        lines.extend(f"- {bullet}" for bullet in bullets[:5])
    if slots:
        lines.append("请围绕以下语义分区组织页面，而不是机械照抄固定构图：")
        lines.extend(f"{index + 1}. {slot}" for index, slot in enumerate(slots[:5]))
    lines.append(f"版式只需大致接近 {layout_family}，无需强行复刻具体卡片数量或指定图标。")
    lines.append("你可以自主决定最适合的视觉重心、流程方向、卡片分组和图标组合。")
    if anchor:
        lines.append(f"统一视觉锚点：{anchor}")
    if style_notes:
        lines.append(f"补充风格说明：{style_notes}")
    lines.append("整体要像成熟企业汇报模板，结构清楚、留白充足、边界明确。")
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
        prefix.append(
            "优先参考上传的风格图，保持整套 PPT 的主色、背景明度和信息图气质一致。"
            "在不偏离整体风格的前提下，可根据本页内容调整模块数量、信息密度和局部构图。"
        )

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

    primitives_desc = ""
    if element_primitives:
        primitives_desc = f"保留以下元素类型：{'、'.join(element_primitives)}。"

    anchor_desc = ""
    if prompt_anchor:
        anchor_desc = f"尽量继承以下风格锚点：{prompt_anchor}。"

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


def collect_page_slots(page: dict[str, Any]) -> list[str]:
    slots = page.get("layout_slots", [])
    if not isinstance(slots, list):
        return []
    return [str(slot).strip() for slot in slots if str(slot).strip()]


def build_style_anchor(style_guide: dict[str, Any] | None = None) -> str:
    style_guide = style_guide or {}
    prompt_anchor = str(style_guide.get("prompt_anchor", "")).strip()
    if prompt_anchor:
        return prompt_anchor

    style_core = style_guide.get("style_core", {})
    if not isinstance(style_core, dict):
        return ""
    return build_prompt_anchor({"style_core": style_core})
