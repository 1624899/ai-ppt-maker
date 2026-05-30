from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any

from ppt_system.generation.design_grammar import normalize_layout_family_name, validate_layout_family
from ppt_system.generation.generation_prompts import build_elements_prompt, build_reference_prompt_by_mode
from ppt_system.generation.page_richness import normalize_page_richness_level
from ppt_system.generation.style_runtime import apply_text_theme
from ppt_system.generation.text_layout import build_fallback_boxes_for_family, build_layout_slots_by_family, build_text_boxes_from_slots


TEXT_INTENT_KEYWORDS = (
    "文字",
    "文案",
    "标题",
    "正文",
    "要点",
    "精简",
    "减少",
    "删减",
    "压缩",
    "错别字",
)
LAYOUT_INTENT_KEYWORDS = (
    "布局",
    "排版",
    "流程",
    "流程图",
    "三栏",
    "三列",
    "时间轴",
    "对比",
    "卡片",
    "留白",
    "紧凑",
    "视觉",
)
STYLE_INTENT_KEYWORDS = (
    "风格",
    "配色",
    "蓝白",
    "科技",
    "商务",
    "极简",
    "深色",
    "浅色",
    "统一",
    "整套",
    "整体",
)
WHOLE_DECK_KEYWORDS = ("整套", "整体", "全套", "全部", "所有", "统一")
COMPACT_TEXT_KEYWORDS = ("精简", "减少", "删减", "压缩", "少一点", "更短")
MORE_SPACE_KEYWORDS = ("留白", "松一点", "更空", "呼吸感")
COMPACT_LAYOUT_KEYWORDS = ("紧凑", "更多内容", "信息密度")


@dataclass(frozen=True)
class EditContext:
    image_width: int
    image_height: int
    style_notes: str
    style_guide: dict[str, Any]
    has_reference_images: bool
    reference_style_adherence: str


@dataclass(frozen=True)
class AgentEditPlan:
    edit_kind: str
    page_numbers: tuple[int, ...]
    requires_image_regeneration: bool
    requires_export_rebuild: bool
    record_only: bool = False


def build_edit_context(state: dict[str, Any]) -> EditContext:
    job_meta = state.get("job_meta", {}) if isinstance(state.get("job_meta"), dict) else {}
    plan = state.get("plan", {}) if isinstance(state.get("plan"), dict) else {}
    image_preset = job_meta.get("image_preset", {}) if isinstance(job_meta.get("image_preset"), dict) else {}
    generation_options = job_meta.get("generation_options")
    if not isinstance(generation_options, dict):
        generation_options = plan.get("generation_options", {}) if isinstance(plan.get("generation_options"), dict) else {}

    return EditContext(
        image_width=_positive_int(image_preset.get("width"), 2048),
        image_height=_positive_int(image_preset.get("height"), 1152),
        style_notes=str(job_meta.get("style_notes") or plan.get("style_notes") or "").strip(),
        style_guide=copy.deepcopy(plan.get("style_guide", {}) if isinstance(plan.get("style_guide"), dict) else {}),
        has_reference_images=bool(job_meta.get("style_reference_images")),
        reference_style_adherence=str(generation_options.get("reference_style_adherence") or "balanced"),
    )


def plan_agent_edit(
    operation_type: str,
    instruction: str,
    *,
    explicit_page_no: int | None,
    available_page_numbers: list[int],
) -> AgentEditPlan:
    if operation_type == "page_text_optimize":
        return AgentEditPlan("text", _required_page_tuple(explicit_page_no), False, True)
    if operation_type == "page_layout_optimize":
        return AgentEditPlan("layout", _required_page_tuple(explicit_page_no), True, True)
    if operation_type == "job_style_adjust":
        return AgentEditPlan("style", tuple(available_page_numbers), True, True)

    page_numbers = tuple(parse_target_page_numbers(instruction, available_page_numbers))
    if explicit_page_no is not None and explicit_page_no not in page_numbers:
        page_numbers = (*page_numbers, explicit_page_no)

    if not page_numbers and _has_any(instruction, WHOLE_DECK_KEYWORDS) and _has_any(instruction, TEXT_INTENT_KEYWORDS):
        page_numbers = tuple(available_page_numbers)

    if page_numbers:
        if _has_any(instruction, LAYOUT_INTENT_KEYWORDS) or _has_any(instruction, STYLE_INTENT_KEYWORDS):
            return AgentEditPlan("layout", page_numbers, True, True)
        if _has_any(instruction, TEXT_INTENT_KEYWORDS):
            return AgentEditPlan("text", page_numbers, False, True)
        return AgentEditPlan("layout", page_numbers, True, True)

    if _has_any(instruction, STYLE_INTENT_KEYWORDS) or _has_any(instruction, WHOLE_DECK_KEYWORDS):
        return AgentEditPlan("style", tuple(available_page_numbers), True, True)

    return AgentEditPlan("record", tuple(), False, False, record_only=True)


def parse_target_page_numbers(instruction: str, available_page_numbers: list[int]) -> list[int]:
    if not instruction:
        return []
    available = set(available_page_numbers)
    result: list[int] = []
    patterns = [
        r"第\s*([一二三四五六七八九十两\d]+)\s*页",
        r"([一二三四五六七八九十两\d]+)\s*页",
    ]
    for pattern in patterns:
        for raw_value in re.findall(pattern, instruction):
            page_no = _parse_page_no(raw_value)
            if page_no in available and page_no not in result:
                result.append(page_no)
    return result


def apply_page_text_edit(
    state: dict[str, Any],
    page_no: int,
    instruction: str,
    payload: dict[str, Any],
    context: EditContext,
) -> dict[str, Any]:
    page = find_page(state, page_no)
    explicit_title = _clean_optional_text(payload.get("title"))
    explicit_summary = _clean_optional_text(payload.get("summary"))
    explicit_bullets = _normalize_bullets(payload.get("bullets"))

    if explicit_title:
        page["title"] = explicit_title
    elif _has_any(instruction, ("标题更短", "短标题", "标题精简")):
        page["title"] = _shorten_text(str(page.get("title") or f"第 {page_no} 页"), 18)

    if explicit_bullets:
        page["bullets"] = explicit_bullets
    elif _has_any(instruction, COMPACT_TEXT_KEYWORDS):
        page["bullets"] = _compact_bullets(page)

    if explicit_summary:
        page["summary"] = explicit_summary
    elif _has_any(instruction, COMPACT_TEXT_KEYWORDS):
        page["summary"] = _compact_summary(page)

    if "bullets" not in page or not isinstance(page.get("bullets"), list):
        page["bullets"] = _derive_bullets(page)

    page["texts"] = rebuild_page_texts(page, context)
    rebuild_page_prompts(page, context)
    append_applied_edit(page, "text", instruction)
    sync_plan_page(state, page)
    return {"page_no": page_no, "edit_kind": "text", "title": page.get("title", "")}


def apply_page_layout_edit(
    state: dict[str, Any],
    page_no: int,
    instruction: str,
    payload: dict[str, Any],
    context: EditContext,
) -> dict[str, Any]:
    page = find_page(state, page_no)
    layout_family = infer_layout_family(instruction, payload.get("layout_family"), str(page.get("layout_family") or "split_left_right"))
    page["layout_family"] = layout_family
    page["page_richness"] = infer_page_richness(instruction, page.get("page_richness"))
    page["layout_slots"] = semantic_slots_for_family(layout_family)
    page["layout_intent"] = _merge_instruction(str(page.get("layout_intent") or ""), instruction)
    page["texts"] = rebuild_page_texts(page, context)
    rebuild_page_prompts(page, context)
    append_applied_edit(page, "layout", instruction)
    sync_plan_page(state, page)
    return {"page_no": page_no, "edit_kind": "layout", "layout_family": layout_family}


def apply_job_style_edit(state: dict[str, Any], instruction: str, context: EditContext) -> dict[str, Any]:
    job_meta = state.setdefault("job_meta", {})
    current_notes = str(job_meta.get("style_notes") or "").strip()
    if instruction:
        job_meta["style_notes"] = _merge_instruction(current_notes, instruction)

    plan = state.setdefault("plan", {})
    if isinstance(plan, dict):
        plan["style_notes"] = str(job_meta.get("style_notes") or "")
        style_guide = plan.setdefault("style_guide", {})
        if isinstance(style_guide, dict):
            style_guide["style_name"] = str(style_guide.get("style_name") or "用户调整后的统一风格")
            style_guide["prompt_anchor"] = _merge_instruction(str(style_guide.get("prompt_anchor") or ""), f"本次风格调整：{instruction}")
            context = EditContext(
                image_width=context.image_width,
                image_height=context.image_height,
                style_notes=str(job_meta.get("style_notes") or ""),
                style_guide=copy.deepcopy(style_guide),
                has_reference_images=context.has_reference_images,
                reference_style_adherence=context.reference_style_adherence,
            )

    edited_pages: list[int] = []
    for page in state.get("pages", []):
        if not isinstance(page, dict):
            continue
        rebuild_page_prompts(page, context)
        append_applied_edit(page, "style", instruction)
        sync_plan_page(state, page)
        edited_pages.append(int(page.get("page_no", 0) or 0))
    return {"edit_kind": "style", "page_numbers": [page_no for page_no in edited_pages if page_no > 0]}


def rebuild_page_texts(page: dict[str, Any], context: EditContext) -> list[dict[str, Any]]:
    title = str(page.get("title") or f"第 {page.get('page_no', '?')} 页").strip()
    body = _build_body_text(page)
    layout_family = str(page.get("layout_family") or "split_left_right").strip()
    page_richness = normalize_page_richness_level(page.get("page_richness") or "medium")
    slots = build_layout_slots_by_family(layout_family, context.image_width, context.image_height, page_richness)
    texts = build_text_boxes_from_slots(slots, title, body, context.image_width, context.image_height)
    if not texts or len(texts) <= 1:
        texts = build_fallback_boxes_for_family(layout_family, title, body, context.image_width, context.image_height)
    return apply_text_theme(texts, context.style_guide)


def rebuild_page_prompts(page: dict[str, Any], context: EditContext) -> None:
    prompt_mode = str(page.get("prompt_profile") or ("slot_brief" if context.has_reference_images else "compact"))
    page["reference_prompt"] = build_reference_prompt_by_mode(
        page,
        context.style_notes,
        context.image_width,
        context.image_height,
        prompt_mode=prompt_mode,
        style_guide=context.style_guide,
        has_reference_images=context.has_reference_images,
        reference_style_adherence=context.reference_style_adherence,
    )
    page["elements_prompt"] = build_elements_prompt(page, context.style_guide)


def infer_layout_family(instruction: str, explicit_value: Any, fallback: str) -> str:
    explicit = normalize_layout_family_name(str(explicit_value or "").strip())
    if validate_layout_family(explicit) and explicit_value:
        return explicit

    text = str(instruction or "")
    keyword_map = [
        (("流程", "路径", "步骤", "链路"), "process_horizontal"),
        (("竖向流程", "纵向流程"), "process_vertical"),
        (("时间轴", "时间线", "里程碑"), "timeline_horizontal"),
        (("纵向时间", "竖向时间"), "timeline_vertical"),
        (("对比", "比较", "左右对照"), "compare_dual_axis"),
        (("三栏", "三列", "网格", "卡片", "矩阵"), "grid_n_x_m"),
        (("中心", "发散", "辐射", "关系图"), "hub_and_spoke"),
        (("上下", "上中下"), "split_top_bottom"),
        (("留白", "大标题", "主视觉"), "hero_with_supporting_cards"),
        (("左右", "两栏", "左图右文", "右图左文"), "split_left_right"),
    ]
    for keywords, family in keyword_map:
        if _has_any(text, keywords):
            return family

    normalized_fallback = normalize_layout_family_name(fallback)
    return normalized_fallback if validate_layout_family(normalized_fallback) else "split_left_right"


def infer_page_richness(instruction: str, fallback: Any) -> str:
    if _has_any(instruction, MORE_SPACE_KEYWORDS):
        return "low"
    if _has_any(instruction, COMPACT_LAYOUT_KEYWORDS):
        return "high"
    return normalize_page_richness_level(fallback or "medium")


def semantic_slots_for_family(layout_family: str) -> list[str]:
    if layout_family == "grid_n_x_m":
        return ["标题区", "卡片区1", "卡片区2", "卡片区3", "卡片区4"]
    if layout_family in {"timeline_horizontal", "timeline_vertical"}:
        return ["标题区", "时间轴", "节点1", "节点2", "节点3"]
    if layout_family in {"process_horizontal", "process_vertical"}:
        return ["标题区", "步骤1", "步骤2", "步骤3"]
    if layout_family == "hub_and_spoke":
        return ["中心主题", "分支1", "分支2", "分支3", "分支4"]
    if layout_family == "split_top_bottom":
        return ["上方内容区", "下方内容区"]
    if layout_family == "compare_dual_axis":
        return ["标题区", "左侧对比项", "右侧对比项", "对比维度"]
    if layout_family == "hero_with_supporting_cards":
        return ["主视觉区", "辅助卡片1", "辅助卡片2", "辅助卡片3"]
    return ["左侧内容区", "右侧内容区"]


def append_applied_edit(page: dict[str, Any], edit_kind: str, instruction: str) -> None:
    edits = page.setdefault("applied_edits", [])
    if not isinstance(edits, list):
        edits = []
        page["applied_edits"] = edits
    edits.append({"kind": edit_kind, "instruction": instruction})
    del edits[:-20]


def sync_plan_page(state: dict[str, Any], page: dict[str, Any]) -> None:
    plan = state.get("plan")
    if not isinstance(plan, dict):
        return
    plan_pages = plan.get("pages")
    if not isinstance(plan_pages, list):
        return
    page_no = int(page.get("page_no", 0) or 0)
    if page_no <= 0:
        return
    sync_fields = {
        "title",
        "summary",
        "bullets",
        "layout_intent",
        "layout_family",
        "layout_slots",
        "page_richness",
        "element_plan",
        "texts",
    }
    for index, plan_page in enumerate(plan_pages):
        if not isinstance(plan_page, dict) or int(plan_page.get("page_no", 0) or 0) != page_no:
            continue
        next_page = copy.deepcopy(plan_page)
        for field in sync_fields:
            if field in page:
                next_page[field] = copy.deepcopy(page[field])
        next_page["image_prompt"] = page.get("reference_prompt", next_page.get("image_prompt", ""))
        plan_pages[index] = next_page
        return


def find_page(state: dict[str, Any], page_no: int) -> dict[str, Any]:
    for page in state.get("pages", []):
        if isinstance(page, dict) and int(page.get("page_no", 0) or 0) == int(page_no):
            return page
    raise ValueError(f"找不到第 {page_no} 页。")


def _build_body_text(page: dict[str, Any]) -> str:
    bullets = page.get("bullets", [])
    if isinstance(bullets, list):
        cleaned = [str(item).strip() for item in bullets if str(item).strip()]
        if cleaned:
            return "\n".join(f"• {item}" for item in cleaned[:6])
    summary = str(page.get("summary") or "").strip()
    if summary:
        return summary
    return ""


def _compact_bullets(page: dict[str, Any]) -> list[str]:
    bullets = _derive_bullets(page)
    compacted = [_shorten_text(item, 28) for item in bullets[:3]]
    return [item for item in compacted if item]


def _compact_summary(page: dict[str, Any]) -> str:
    summary = str(page.get("summary") or "").strip()
    if summary:
        first_sentence = re.split(r"[。！？!?；;]\s*", summary)[0].strip()
        return _shorten_text(first_sentence or summary, 60)
    bullets = _compact_bullets(page)
    return "；".join(bullets[:2])


def _derive_bullets(page: dict[str, Any]) -> list[str]:
    bullets = page.get("bullets", [])
    if isinstance(bullets, list) and bullets:
        return [str(item).strip().lstrip("•").strip() for item in bullets if str(item).strip()]
    summary = str(page.get("summary") or "").strip()
    if not summary:
        return []
    parts = re.split(r"[。！？!?；;\n]+", summary)
    return [part.strip() for part in parts if part.strip()]


def _normalize_bullets(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip().lstrip("•").strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        parts = re.split(r"[\n；;]+", value)
        return [part.strip().lstrip("•").strip() for part in parts if part.strip()]
    return []


def _clean_optional_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _shorten_text(value: str, limit: int) -> str:
    text = " ".join(str(value or "").strip().split())
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def _merge_instruction(current: str, instruction: str) -> str:
    clean_current = str(current or "").strip()
    clean_instruction = str(instruction or "").strip()
    if not clean_instruction:
        return clean_current
    if not clean_current:
        return clean_instruction
    if clean_instruction in clean_current:
        return clean_current
    return f"{clean_current}；{clean_instruction}"


def _has_any(text: str, keywords: tuple[str, ...]) -> bool:
    source = str(text or "")
    return any(keyword in source for keyword in keywords)


def _required_page_tuple(page_no: int | None) -> tuple[int, ...]:
    if page_no is None:
        raise ValueError("页面级操作缺少 page_no。")
    return (page_no,)


def _parse_page_no(value: str) -> int:
    text = str(value or "").strip()
    if text.isdigit():
        return int(text)
    return _parse_chinese_number(text)


def _parse_chinese_number(text: str) -> int:
    digits = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if not text:
        return 0
    if text == "十":
        return 10
    if "十" in text:
        left, _, right = text.partition("十")
        tens = digits.get(left, 1) if left else 1
        ones = digits.get(right, 0) if right else 0
        return tens * 10 + ones
    return digits.get(text, 0)


def _positive_int(value: Any, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return number if number > 0 else fallback
