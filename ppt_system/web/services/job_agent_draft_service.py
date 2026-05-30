from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from flask import jsonify, request

from ppt_system.web.runtime import get_runtime_module
from ppt_system.web.services.job_edit_planner import (
    LAYOUT_INTENT_KEYWORDS,
    STYLE_INTENT_KEYWORDS,
    TEXT_INTENT_KEYWORDS,
    WHOLE_DECK_KEYWORDS,
    parse_target_page_numbers,
)


MAX_AGENT_TURNS = 80
MAX_AGENT_CONTEXT_MESSAGES = 12


@dataclass(frozen=True)
class AgentDraft:
    draft_id: str
    operation_type: str
    edit_kind: str
    page_no: int | None
    affected_pages: list[int]
    instruction: str
    summary: str
    changes: list[str]
    confidence: str
    needs_confirmation: bool = True
    image_annotations: list[dict[str, Any]] | None = None


def api_create_agent_draft(job_id: str):
    payload = request.get_json(silent=True) or {}
    try:
        result = create_agent_draft(job_id, payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify(result)


def create_agent_draft(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    runtime = get_runtime_module()
    record = runtime.get_job_record(runtime.JOBS_DB_PATH, job_id)
    if not record:
        raise FileNotFoundError("任务不存在")
    job_dir = Path(record["job_dir"])
    state, _ = runtime.get_job_state_snapshot(job_id, job_dir)
    if not state:
        raise FileNotFoundError("任务状态不存在")

    user_message = _normalize_text(payload.get("message"))
    if not user_message:
        raise ValueError("请先描述你想让 Agent 理解的问题或修改方向。")

    selected_page_no = _optional_page_no(payload.get("page_no"))
    selected_preview = _normalize_text(payload.get("preview_type")) or "reference"
    messages = _normalize_messages(payload.get("messages"))
    annotations = _normalize_annotations(payload.get("annotations"))
    page_numbers = _collect_page_numbers(state)
    draft = plan_agent_draft(
        user_message,
        state,
        selected_page_no=selected_page_no,
        available_page_numbers=page_numbers,
        annotations=annotations,
    )

    now = _timestamp()
    user_turn = {
        "turn_id": uuid.uuid4().hex[:12],
        "role": "user",
        "message": user_message,
        "page_no": selected_page_no,
        "preview_type": selected_preview,
        "annotations": annotations,
        "created_at": now,
    }
    assistant_turn = {
        "turn_id": uuid.uuid4().hex[:12],
        "role": "assistant",
        "message": draft.summary,
        "draft": asdict(draft),
        "created_at": now,
    }

    def updater(current_state: dict[str, Any]) -> None:
        turns = current_state.setdefault("agent_conversation", [])
        if not isinstance(turns, list):
            turns = []
            current_state["agent_conversation"] = turns
        if messages and not turns:
            turns.extend(_seed_client_messages(messages))
        turns.extend([user_turn, assistant_turn])
        del turns[:-MAX_AGENT_TURNS]
        current_state["agent_pending_draft"] = asdict(draft)

    updated_state = runtime.mutate_job_state(job_dir, job_id, updater)
    return {
        "draft": asdict(draft),
        "messages": (updated_state.get("agent_conversation") if isinstance(updated_state, dict) else []) or [],
    }


def plan_agent_draft(
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


def _normalize_messages(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value[-MAX_AGENT_CONTEXT_MESSAGES:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        if role not in {"user", "assistant"}:
            continue
        text = _normalize_text(item.get("message") or item.get("content"))
        if not text:
            continue
        normalized.append({"role": role, "message": text})
    return normalized


def _seed_client_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now = _timestamp()
    return [
        {
            "turn_id": uuid.uuid4().hex[:12],
            "role": message["role"],
            "message": message["message"],
            "created_at": now,
            "source": "client_context",
        }
        for message in messages
    ]


def _normalize_annotations(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    annotations: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        box = item.get("box") if isinstance(item.get("box"), dict) else item
        normalized_box = {
            "x": _ratio(box.get("x")),
            "y": _ratio(box.get("y")),
            "width": _ratio(box.get("width")),
            "height": _ratio(box.get("height")),
        }
        if normalized_box["width"] <= 0 or normalized_box["height"] <= 0:
            continue
        annotations.append(
            {
                "id": str(item.get("id") or uuid.uuid4().hex[:8]),
                "label": _normalize_text(item.get("label")) or f"标注 {len(annotations) + 1}",
                "box": normalized_box,
            }
        )
    return annotations[:20]


def _collect_page_numbers(state: dict[str, Any]) -> list[int]:
    numbers: list[int] = []
    for page in state.get("pages", []):
        if not isinstance(page, dict):
            continue
        page_no = _optional_page_no(page.get("page_no"))
        if page_no and page_no not in numbers:
            numbers.append(page_no)
    numbers.sort()
    return numbers


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


def _ratio(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number < 0:
        return 0.0
    if number > 1:
        return 1.0
    return number


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _has_any(text: str, keywords: tuple[str, ...]) -> bool:
    source = str(text or "")
    return any(keyword in source for keyword in keywords)


def _timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
