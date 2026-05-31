from __future__ import annotations

import uuid
from typing import Any

from ppt_system.web.services.job_agent_draft_models import AgentDraft
from ppt_system.web.services.job_edit_planner import (
    LAYOUT_INTENT_KEYWORDS,
    STYLE_INTENT_KEYWORDS,
    TEXT_INTENT_KEYWORDS,
    WHOLE_DECK_KEYWORDS,
    parse_target_page_numbers,
)


def plan_agent_draft_by_rules(
    user_message: str,
    state: dict[str, Any],
    *,
    selected_page_no: int | None,
    available_page_numbers: list[int],
    annotations: list[dict[str, Any]] | None = None,
) -> AgentDraft:
    instruction = _normalize_text(user_message)
    page_numbers = parse_target_page_numbers(instruction, available_page_numbers)
    if selected_page_no and selected_page_no in available_page_numbers and selected_page_no not in page_numbers:
        page_numbers = [selected_page_no, *page_numbers]
    if not page_numbers and _has_any(instruction, WHOLE_DECK_KEYWORDS):
        page_numbers = list(available_page_numbers)
    if not page_numbers and selected_page_no and selected_page_no in available_page_numbers:
        page_numbers = [selected_page_no]

    edit_kind = infer_draft_edit_kind(instruction, annotations or [])
    if edit_kind == "style" and _has_any(instruction, WHOLE_DECK_KEYWORDS):
        page_numbers = list(available_page_numbers)

    operation_type = operation_type_for_edit_kind(edit_kind)
    page_no = page_numbers[0] if len(page_numbers) == 1 else None
    title = _page_title(state, page_no) if page_no else ""
    changes = build_change_items(instruction, edit_kind, page_numbers, annotations or [])
    summary = build_draft_summary(edit_kind, page_numbers, title, changes)
    confidence = "high" if _has_any(instruction, TEXT_INTENT_KEYWORDS + LAYOUT_INTENT_KEYWORDS + STYLE_INTENT_KEYWORDS) else "medium"

    return AgentDraft(
        draft_id=uuid.uuid4().hex[:12],
        operation_type=operation_type,
        edit_kind=edit_kind,
        page_no=page_no,
        affected_pages=page_numbers,
        instruction=build_structured_instruction(instruction, edit_kind, page_numbers, annotations or []),
        summary=summary,
        changes=changes,
        confidence=confidence,
        image_annotations=annotations or [],
    )


def infer_draft_edit_kind(instruction: str, annotations: list[dict[str, Any]]) -> str:
    if annotations and _has_any(instruction, ("图片", "图", "画面", "位置", "区域", "这块", "这里", "框选")):
        return "layout"
    if _has_any(instruction, STYLE_INTENT_KEYWORDS):
        return "style" if _has_any(instruction, WHOLE_DECK_KEYWORDS) else "layout"
    if _has_any(instruction, LAYOUT_INTENT_KEYWORDS):
        return "layout"
    if _has_any(instruction, TEXT_INTENT_KEYWORDS):
        return "text"
    return "layout"


def operation_type_for_edit_kind(edit_kind: str) -> str:
    if edit_kind == "text":
        return "page_text_optimize"
    if edit_kind == "style":
        return "job_style_adjust"
    return "page_layout_optimize"


def build_structured_instruction(
    instruction: str,
    edit_kind: str,
    page_numbers: list[int],
    annotations: list[dict[str, Any]],
) -> str:
    prefix = _format_page_scope(page_numbers)
    kind_label = {"text": "文字修改", "layout": "画面与排版修改", "style": "整体风格修改"}.get(edit_kind, "修改")
    parts = [f"{prefix}{kind_label}：{instruction}"]
    if annotations:
        parts.append(f"原稿图标注区域：{_format_annotations(annotations)}")
    return "；".join(part for part in parts if part)


def build_change_items(
    instruction: str,
    edit_kind: str,
    page_numbers: list[int],
    annotations: list[dict[str, Any]],
) -> list[str]:
    changes: list[str] = []
    scope = _format_page_scope(page_numbers)
    if edit_kind == "text":
        changes.append(f"{scope}按反馈优化标题、正文和要点表达。")
        if _has_any(instruction, ("减少", "精简", "删减", "压缩", "少一点")):
            changes.append("减少文字密度，优先保留核心结论和关键词。")
    elif edit_kind == "style":
        changes.append("统一整套 PPT 的风格提示词、配色和视觉气质。")
        changes.append(f"将用户描述沉淀为后续原稿图与元素图重绘约束：{instruction}")
    else:
        changes.append(f"{scope}调整原稿图画面、布局层级或视觉重心。")
        if _has_any(instruction, ("流程", "步骤", "路径")):
            changes.append("优先整理为流程/路径结构，强化阅读顺序。")
        if _has_any(instruction, ("乱", "拥挤", "挤", "密")):
            changes.append("降低拥挤感，增加留白并拉开模块层级。")
    if annotations:
        changes.append(f"结合 {len(annotations)} 个框选标注区域定位修改对象。")
    if len(changes) < 2:
        changes.append(f"保留原有主题内容，只改动用户指出的问题：{instruction}")
    return changes


def build_draft_summary(edit_kind: str, page_numbers: list[int], page_title: str, changes: list[str]) -> str:
    scope = _format_page_scope(page_numbers)
    target = f"{scope}「{page_title}」" if page_title and len(page_numbers) == 1 else scope
    kind_label = {"text": "文字", "layout": "原稿图/排版", "style": "整套风格"}.get(edit_kind, "内容")
    preview = "；".join(changes[:2])
    return f"我理解你想调整{target}的{kind_label}。具体会整理为：{preview}"


def _page_title(state: dict[str, Any], page_no: int | None) -> str:
    if page_no is None:
        return ""
    for page in state.get("pages", []):
        if isinstance(page, dict) and _optional_page_no(page.get("page_no")) == page_no:
            return _normalize_text(page.get("title")) or f"第 {page_no} 页"
    return f"第 {page_no} 页"


def _format_page_scope(page_numbers: list[int]) -> str:
    clean_numbers = [page_no for page_no in page_numbers if page_no > 0]
    if not clean_numbers:
        return "当前 PPT "
    if len(clean_numbers) == 1:
        return f"第 {clean_numbers[0]} 页"
    if len(clean_numbers) > 6:
        return "整套 PPT "
    return f"第 {'、'.join(str(page_no) for page_no in clean_numbers)} 页"


def _format_annotations(annotations: list[dict[str, Any]]) -> str:
    labels = []
    for index, annotation in enumerate(annotations, start=1):
        label = _normalize_text(annotation.get("label")) or f"区域 {index}"
        box = annotation.get("box") if isinstance(annotation.get("box"), dict) else {}
        labels.append(f"{label}({round(float(box.get('x', 0)) * 100)}%, {round(float(box.get('y', 0)) * 100)}%)")
    return "、".join(labels)


def _optional_page_no(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        page_no = int(value)
    except (TypeError, ValueError):
        return None
    return page_no if page_no > 0 else None


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _has_any(text: str, keywords: tuple[str, ...]) -> bool:
    source = str(text or "")
    return any(keyword in source for keyword in keywords)
