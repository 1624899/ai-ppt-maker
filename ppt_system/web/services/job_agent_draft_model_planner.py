from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from ppt_system.integrations.model_config import get_active_model_config
from ppt_system.integrations.openai_chat_provider import OpenAIChatProvider
from ppt_system.web.services.job_agent_draft_models import AgentDraft
from ppt_system.web.services.job_edit_planner import WHOLE_DECK_KEYWORDS, parse_target_page_numbers


VALID_EDIT_KINDS = {"text", "layout", "style"}
VALID_CONFIDENCES = {"low", "medium", "high"}
MODEL_CONTEXT_PAGE_LIMIT = 12


SYSTEM_PROMPT = """
你是一个 PPT 原稿图改稿 Agent，职责不是直接生成 PPT，而是把用户模糊、口语化的反馈理解成可确认的具体改动草案。

工作流：
1. 用户已经在右侧选中某一页的原稿图或元素图，可能还框选了区域。
2. 用户会用自然语言描述“哪里不对”“哪里要改”，表达可能很模糊。
3. 你需要结合当前页、图片、标注区域、任务上下文和最近多轮对话，整理出明确、可执行的改动内容。
4. 你必须等待用户确认，因此 needs_confirmation 固定为 true，不要声称已经执行生成。

判断规则：
- edit_kind 为 text：只改标题、正文、要点、措辞、文字密度。
- edit_kind 为 layout：改原稿图画面、模块层级、卡片、图标、位置、留白、视觉重心、单页风格表现。
- edit_kind 为 style：只用于整套 PPT 的统一风格、配色、视觉气质调整。
- style 必须影响整套 PPT；如果只是当前页“更商务/更科技”，应归为 layout。

返回要求：
- 只返回严格 JSON，不要 Markdown。
- affected_pages 只能使用可用页码；如果用户说“这里/这块/当前页”，使用 selected_page_no。
- summary 用中文自然回复用户，说明“我理解为……”，并列出等待确认的改动方向。
- changes 必须是具体动作，不要写空泛建议。
- instruction 是确认后要带入编辑页的完整改动指令，应包含页码范围、对象、问题和目标效果。
""".strip()


def plan_agent_draft_with_model(
    *,
    config: dict[str, Any],
    job_id: str,
    job_dir: Path,
    state: dict[str, Any],
    user_message: str,
    selected_page_no: int | None,
    selected_preview: str,
    available_page_numbers: list[int],
    annotations: list[dict[str, Any]],
    messages: list[dict[str, Any]],
) -> AgentDraft:
    chat_profile = get_active_model_config(config, "chat")
    provider = OpenAIChatProvider(config, chat_profile)
    request_messages = build_agent_model_messages(
        provider=provider,
        job_id=job_id,
        job_dir=job_dir,
        state=state,
        user_message=user_message,
        selected_page_no=selected_page_no,
        selected_preview=selected_preview,
        available_page_numbers=available_page_numbers,
        annotations=annotations,
        messages=messages,
    )
    result = provider.complete_json(request_messages)
    return normalize_model_draft(
        result,
        state=state,
        user_message=user_message,
        selected_page_no=selected_page_no,
        available_page_numbers=available_page_numbers,
        annotations=annotations,
    )


def build_agent_model_messages(
    *,
    provider: OpenAIChatProvider,
    job_id: str,
    job_dir: Path,
    state: dict[str, Any],
    user_message: str,
    selected_page_no: int | None,
    selected_preview: str,
    available_page_numbers: list[int],
    annotations: list[dict[str, Any]],
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    context = build_prompt_context(
        state=state,
        user_message=user_message,
        selected_page_no=selected_page_no,
        selected_preview=selected_preview,
        available_page_numbers=available_page_numbers,
        annotations=annotations,
        messages=messages,
    )
    content_items: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": build_user_prompt(context),
        }
    ]
    image_path = resolve_selected_preview_image(job_dir, job_id, state, selected_page_no, selected_preview)
    if image_path is not None:
        content_items.append(provider.build_image_message_item(image_path))

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": content_items},
    ]


def build_prompt_context(
    *,
    state: dict[str, Any],
    user_message: str,
    selected_page_no: int | None,
    selected_preview: str,
    available_page_numbers: list[int],
    annotations: list[dict[str, Any]],
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    job_meta = state.get("job_meta") if isinstance(state.get("job_meta"), dict) else {}
    plan = state.get("plan") if isinstance(state.get("plan"), dict) else {}
    selected_page = find_page_summary(state, selected_page_no)
    return {
        "task": {
            "title": str(job_meta.get("title") or job_meta.get("content") or state.get("title") or "")[:240],
            "style_notes": str(job_meta.get("style_notes") or plan.get("style_notes") or ""),
            "current_status": str(state.get("status") or ""),
        },
        "available_page_numbers": available_page_numbers,
        "selected": {
            "page_no": selected_page_no,
            "preview_type": selected_preview,
            "page": selected_page,
        },
        "pages": summarize_pages(state),
        "annotations": annotations,
        "recent_conversation": messages,
        "latest_user_message": user_message,
        "output_schema": {
            "edit_kind": "text | layout | style",
            "affected_pages": [selected_page_no] if selected_page_no else [],
            "summary": "中文自然回复，说明你整理出的改动草案",
            "changes": ["具体动作1", "具体动作2"],
            "instruction": "确认后带入编辑页的完整改动指令",
            "confidence": "low | medium | high",
            "needs_confirmation": True,
        },
    }


def build_user_prompt(context: dict[str, Any]) -> str:
    return (
        "请根据下面上下文，把用户最新反馈整理为一个等待确认的 PPT 改稿草案。"
        "如果图片已随消息附上，请优先结合图片中可见的视觉问题；如果图片不可用，请依据页面摘要、标注和对话理解。"
        "务必只返回 JSON。\n\n"
        f"{json.dumps(context, ensure_ascii=False, indent=2)}"
    )


def normalize_model_draft(
    result: dict[str, Any],
    *,
    state: dict[str, Any],
    user_message: str,
    selected_page_no: int | None,
    available_page_numbers: list[int],
    annotations: list[dict[str, Any]],
) -> AgentDraft:
    if not isinstance(result, dict):
        raise ValueError("模型没有返回 JSON 对象。")

    edit_kind = normalize_edit_kind(result.get("edit_kind"), result.get("operation_type"))
    affected_pages = normalize_affected_pages(
        result.get("affected_pages") or result.get("page_numbers") or result.get("pages"),
        available_page_numbers,
    )
    text_for_page_parse = " ".join(
        _normalize_text(part)
        for part in (
            user_message,
            result.get("summary"),
            result.get("instruction"),
            " ".join(_normalize_string_list(result.get("changes"))),
        )
        if _normalize_text(part)
    )
    if not affected_pages:
        affected_pages = parse_target_page_numbers(text_for_page_parse, available_page_numbers)
    if edit_kind == "style":
        affected_pages = list(available_page_numbers)
    if not affected_pages and selected_page_no and selected_page_no in available_page_numbers:
        affected_pages = [selected_page_no]
    if not affected_pages and _has_any(text_for_page_parse, WHOLE_DECK_KEYWORDS):
        affected_pages = list(available_page_numbers)

    operation_type = normalize_operation_type(result.get("operation_type"), edit_kind)
    page_no = affected_pages[0] if len(affected_pages) == 1 else None
    changes = _normalize_string_list(result.get("changes") or result.get("change_items") or result.get("actions"))
    if not changes:
        raise ValueError("模型返回缺少 changes，无法生成对话回复。")
    changes = changes[:6]

    instruction = _normalize_text(result.get("instruction"))
    if not instruction:
        raise ValueError("模型返回缺少 instruction，无法生成对话回复。")
    elif annotations:
        instruction = append_annotation_labels(instruction, annotations)

    summary = _normalize_text(result.get("summary") or result.get("message"))
    if not summary:
        raise ValueError("模型返回缺少 summary，无法生成对话回复。")

    confidence = _normalize_text(result.get("confidence")).lower()
    if confidence not in VALID_CONFIDENCES:
        confidence = "medium"

    return AgentDraft(
        draft_id=uuid.uuid4().hex[:12],
        operation_type=operation_type,
        edit_kind=edit_kind,
        page_no=page_no,
        affected_pages=affected_pages,
        instruction=instruction,
        summary=summary,
        changes=changes,
        confidence=confidence,
        needs_confirmation=True,
        image_annotations=annotations,
    )


def normalize_edit_kind(value: Any, operation_type: Any) -> str:
    edit_kind = _normalize_text(value).lower()
    if edit_kind in VALID_EDIT_KINDS:
        return edit_kind
    operation = _normalize_text(operation_type)
    if operation == "page_text_optimize":
        return "text"
    if operation == "job_style_adjust":
        return "style"
    if operation == "page_layout_optimize":
        return "layout"
    raise ValueError("模型返回缺少有效 edit_kind，无法生成对话回复。")


def normalize_operation_type(value: Any, edit_kind: str) -> str:
    operation_type = _normalize_text(value)
    valid = {"page_text_optimize", "page_layout_optimize", "job_style_adjust"}
    if operation_type in valid:
        return operation_type
    if edit_kind == "text":
        return "page_text_optimize"
    if edit_kind == "style":
        return "job_style_adjust"
    return "page_layout_optimize"


def normalize_affected_pages(value: Any, available_page_numbers: list[int]) -> list[int]:
    available = set(available_page_numbers)
    raw_items = value if isinstance(value, list) else [value]
    result: list[int] = []
    for item in raw_items:
        page_no = _optional_page_no(item)
        if page_no and page_no in available and page_no not in result:
            result.append(page_no)
    return result


def summarize_pages(state: dict[str, Any]) -> list[dict[str, Any]]:
    pages = state.get("pages", [])
    summaries: list[dict[str, Any]] = []
    if not isinstance(pages, list):
        return summaries
    for page in pages[:MODEL_CONTEXT_PAGE_LIMIT]:
        if not isinstance(page, dict):
            continue
        summaries.append(summarize_page(page))
    return summaries


def find_page_summary(state: dict[str, Any], page_no: int | None) -> dict[str, Any]:
    if page_no is None:
        return {}
    for page in state.get("pages", []):
        if isinstance(page, dict) and _optional_page_no(page.get("page_no")) == page_no:
            return summarize_page(page)
    return {}


def summarize_page(page: dict[str, Any]) -> dict[str, Any]:
    return {
        "page_no": _optional_page_no(page.get("page_no")),
        "title": _normalize_text(page.get("title")),
        "summary": _normalize_text(page.get("summary")),
        "bullets": _normalize_string_list(page.get("bullets"))[:6],
        "layout_intent": _normalize_text(page.get("layout_intent")),
        "layout_family": _normalize_text(page.get("layout_family")),
        "page_richness": _normalize_text(page.get("page_richness")),
        "reference_prompt": _truncate(_normalize_text(page.get("reference_prompt")), 420),
    }


def resolve_selected_preview_image(
    job_dir: Path,
    job_id: str,
    state: dict[str, Any],
    selected_page_no: int | None,
    selected_preview: str,
) -> Path | None:
    if selected_page_no is None:
        return None
    image_value = ""
    image_field = "element_image" if selected_preview == "element" else "reference_image"
    collection_key = "element_pages" if selected_preview == "element" else "reference_pages"
    for page in state.get("pages", []):
        if isinstance(page, dict) and _optional_page_no(page.get("page_no")) == selected_page_no:
            image_value = _normalize_text(page.get(image_field))
            break
    if not image_value:
        for item in state.get(collection_key, []):
            if isinstance(item, dict) and _optional_page_no(item.get("page_no")) == selected_page_no:
                image_value = _normalize_text(item.get("image"))
                break
    return resolve_job_artifact_path(job_dir, job_id, image_value)


def resolve_job_artifact_path(job_dir: Path, job_id: str, value: str) -> Path | None:
    raw_value = _normalize_text(value)
    if not raw_value:
        return None
    path: Path
    run_prefix = f"/runs/{job_id}/"
    if raw_value.startswith(run_prefix):
        path = job_dir / raw_value[len(run_prefix):]
    elif raw_value.startswith(f"runs/{job_id}/"):
        path = job_dir / raw_value[len(f"runs/{job_id}/"):]
    else:
        candidate = Path(raw_value)
        path = candidate if candidate.is_absolute() else job_dir / raw_value.lstrip("/\\")
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        return None
    return path if path.exists() else None


def append_annotation_labels(instruction: str, annotations: list[dict[str, Any]]) -> str:
    labels = [_normalize_text(annotation.get("label")) for annotation in annotations if _normalize_text(annotation.get("label"))]
    if not labels or any(label in instruction for label in labels):
        return instruction
    return f"{instruction}；参考框选区域：{'、'.join(labels)}"


def _page_title(state: dict[str, Any], page_no: int | None) -> str:
    if page_no is None:
        return ""
    for page in state.get("pages", []):
        if isinstance(page, dict) and _optional_page_no(page.get("page_no")) == page_no:
            return _normalize_text(page.get("title")) or f"第 {page_no} 页"
    return f"第 {page_no} 页"


def _normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_normalize_text(item) for item in value if _normalize_text(item)]
    if isinstance(value, str) and value.strip():
        return [_normalize_text(part) for part in value.replace("；", "\n").splitlines() if _normalize_text(part)]
    return []


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


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: max(1, limit - 1)].rstrip()}…"


def _has_any(text: str, keywords: tuple[str, ...]) -> bool:
    source = str(text or "")
    return any(keyword in source for keyword in keywords)
