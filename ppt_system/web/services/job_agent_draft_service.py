from __future__ import annotations

import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from flask import jsonify, request

from ppt_system.web.runtime import get_runtime_module
from ppt_system.web.services.app_config_runtime import resolve_image_preset
from ppt_system.web.services.job_agent_draft_model_planner import plan_agent_draft_with_model
from ppt_system.web.services.job_agent_draft_models import AgentDraft
from ppt_system.web.services.job_submission_runtime import build_active_config


MAX_AGENT_TURNS = 80
MAX_AGENT_CONTEXT_MESSAGES = 12


def api_create_agent_draft(job_id: str):
    payload = request.get_json(silent=True) or {}
    try:
        result = create_agent_draft(job_id, payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": f"Agent 模型理解失败：{exc}"}), 502
    return jsonify(result)


def api_clear_agent_conversation(job_id: str):
    try:
        result = clear_agent_conversation(job_id)
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
    config = runtime.read_config()
    active_config = _resolve_agent_active_config(config, record)
    draft, draft_meta = plan_agent_draft(
        user_message,
        state,
        selected_page_no=selected_page_no,
        selected_preview=selected_preview,
        available_page_numbers=page_numbers,
        annotations=annotations,
        messages=messages,
        config=active_config,
        job_id=job_id,
        job_dir=job_dir,
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
        "agent_meta": draft_meta,
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
        current_state["agent_pending_draft_meta"] = draft_meta

    updated_state = runtime.mutate_job_state(job_dir, job_id, updater)
    return {
        "draft": asdict(draft),
        "messages": (updated_state.get("agent_conversation") if isinstance(updated_state, dict) else []) or [],
        "agent_meta": draft_meta,
    }


def clear_agent_conversation(job_id: str) -> dict[str, Any]:
    runtime = get_runtime_module()
    record = runtime.get_job_record(runtime.JOBS_DB_PATH, job_id)
    if not record:
        raise FileNotFoundError("任务不存在")
    job_dir = Path(record["job_dir"])
    state, _ = runtime.get_job_state_snapshot(job_id, job_dir)
    if not state:
        raise FileNotFoundError("任务状态不存在")

    def updater(current_state: dict[str, Any]) -> None:
        current_state["agent_conversation"] = []
        current_state["agent_pending_draft"] = None
        current_state["agent_pending_draft_meta"] = None

    updated_state = runtime.mutate_job_state(job_dir, job_id, updater)
    return {
        **updated_state,
        "ok": True,
        "messages": updated_state.get("agent_conversation", []),
        "agent_pending_draft": updated_state.get("agent_pending_draft"),
    }


def plan_agent_draft(
    user_message: str,
    state: dict[str, Any],
    *,
    selected_page_no: int | None,
    available_page_numbers: list[int],
    annotations: list[dict[str, Any]] | None = None,
    selected_preview: str = "reference",
    messages: list[dict[str, Any]] | None = None,
    config: dict[str, Any] | None = None,
    job_id: str = "",
    job_dir: Path | None = None,
) -> tuple[AgentDraft, dict[str, Any]]:
    normalized_annotations = annotations or []
    if not config or not _has_chat_model_config(config) or job_dir is None or not job_id:
        raise ValueError("请先在设置中配置可用的对话模型。")
    draft = plan_agent_draft_with_model(
        config=config,
        job_id=job_id,
        job_dir=job_dir,
        state=state,
        user_message=user_message,
        selected_page_no=selected_page_no,
        selected_preview=selected_preview,
        available_page_numbers=available_page_numbers,
        annotations=normalized_annotations,
        messages=messages or [],
    )
    return draft, {"planner": "model", "fallback_used": False}


def _has_chat_model_config(config: dict[str, Any]) -> bool:
    model_configs = config.get("model_configs") if isinstance(config.get("model_configs"), dict) else {}
    chat_configs = model_configs.get("chat") if isinstance(model_configs.get("chat"), list) else []
    for item in chat_configs:
        if not isinstance(item, dict):
            continue
        if str(item.get("model") or "").strip() and str(item.get("base_url") or "").strip() and str(item.get("api_key") or "").strip():
            return True
    return False


def _resolve_agent_active_config(config: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    request_payload = record.get("request", {}) if isinstance(record.get("request"), dict) else {}
    try:
        image_preset = resolve_image_preset(
            config,
            str(request_payload.get("image_preset") or config.get("default_image_preset", "")),
        )
        image_quality = str(request_payload.get("image_quality") or record.get("image_quality") or config.get("image_quality", "medium"))
        return build_active_config(config, image_preset, image_quality)
    except Exception:
        return dict(config)


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
            "x": _ratio(box.get("x")) if isinstance(box, dict) else 0.0,
            "y": _ratio(box.get("y")) if isinstance(box, dict) else 0.0,
            "width": _ratio(box.get("width")) if isinstance(box, dict) else 0.0,
            "height": _ratio(box.get("height")) if isinstance(box, dict) else 0.0,
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


def _timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
