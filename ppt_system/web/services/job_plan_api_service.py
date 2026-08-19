from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import jsonify, request

from ppt_system.generation.planning_state import has_complete_planning_state
from ppt_system.jobs.job_interrupt_signal import clear_job_stop_request
from ppt_system.jobs.job_store import get_job as get_job_record
from ppt_system.jobs.job_store import update_job as update_job_record
from ppt_system.runtime import runtime_context
from ppt_system.web.services.api_response import api_error
from ppt_system.web.services.job_api_common import _get_existing_job_record, _load_editable_job_state, _set_stage_status
from ppt_system.web.services.job_state_store import load_job_state, mutate_job_state
from ppt_system.web.services.job_plan_record_sync import sync_plan_metadata_to_job_record
from ppt_system.web.services.job_submission_runtime import submit_existing_job_pipeline
from ppt_system.web.services.plan_version_store import (
    apply_plan_to_state,
    build_plan_response,
    get_active_plan_payload,
    save_plan_version,
)
from ppt_system.web.services.workflow_policy import (
    AWAITING_PLAN_CONFIRMATION_STATUS,
    ensure_workflow_metadata,
    mark_plan_confirmed,
    mark_plan_draft,
    normalize_workflow_mode,
)

def api_get_job_plan(job_id: str):
    record = _get_existing_job_record(job_id)
    if not record:
        return api_error("任务不存在", 404)
    job_dir = Path(record["job_dir"])
    state = _load_editable_job_state(record, job_dir)
    if not state:
        return api_error("任务状态不存在", 404)
    ensure_workflow_metadata(state, record.get("request", {}))
    return jsonify(build_plan_response(state))

def api_update_job_plan(job_id: str):
    record = _get_existing_job_record(job_id)
    if not record:
        return api_error("任务不存在", 404)
    if str(record.get("status") or "").strip() in {"queued", "running", "stopping"}:
        return api_error("任务正在执行中，请先暂停或等待当前阶段完成。")

    payload = request.get_json(silent=True) or {}
    raw_plan = payload.get("plan", payload)
    if not isinstance(raw_plan, dict):
        return api_error("规划内容必须是对象。")

    job_dir = Path(record["job_dir"])

    def updater(state: dict[str, Any]) -> None:
        ensure_workflow_metadata(state, record.get("request", {}))
        normalized_plan = apply_plan_to_state(state, raw_plan)
        save_plan_version(
            state,
            source="user_draft",
            summary=str(payload.get("summary") or "用户保存规划草案"),
            plan=normalized_plan,
        )
        mark_plan_draft(state)
        state["status"] = AWAITING_PLAN_CONFIRMATION_STATUS
        state["current_stage"] = "planning"
        state["error"] = ""
        state["stop_requested"] = False
        _set_stage_status(
            state,
            "planning",
            status="completed",
            summary="规划草案已保存，等待确认后继续生成",
        )

    updated_state = mutate_job_state(job_dir, job_id, updater)
    sync_plan_metadata_to_job_record(runtime_context.JOBS_DB_PATH, job_id, updated_state)
    return jsonify(build_plan_response(updated_state))

def api_confirm_job_plan(job_id: str):
    record = _get_existing_job_record(job_id)
    if not record:
        return api_error("任务不存在", 404)
    if str(record.get("status") or "").strip() in {"queued", "running", "stopping"}:
        return api_error("任务正在执行中，不能重复确认规划。")

    payload = request.get_json(silent=True) or {}
    raw_plan = payload.get("plan")
    if raw_plan is not None and not isinstance(raw_plan, dict):
        return api_error("规划内容必须是对象。")

    job_dir = Path(record["job_dir"])
    request_payload = dict(record.get("request", {}) if isinstance(record.get("request"), dict) else {})

    def updater(state: dict[str, Any]) -> None:
        ensure_workflow_metadata(state, request_payload)
        if isinstance(raw_plan, dict):
            normalized_plan = apply_plan_to_state(state, raw_plan)
        else:
            normalized_plan = get_active_plan_payload(state)
        if not has_complete_planning_state(state):
            raise ValueError("当前规划缺少页面标题或原稿图提示词，暂时不能继续生成。")
        save_plan_version(
            state,
            source="user_confirmed",
            summary=str(payload.get("summary") or "用户确认规划"),
            plan=normalized_plan,
        )
        mark_plan_confirmed(state)
        state["status"] = "queued"
        state["current_stage"] = "planning"
        state["error"] = ""
        state["stop_requested"] = False
        _set_stage_status(
            state,
            "planning",
            status="completed",
            summary=f"规划已确认，共 {len(state.get('pages', []))} 页",
        )

    try:
        updated_state = mutate_job_state(job_dir, job_id, updater)
    except ValueError as exc:
        return api_error(exc)

    refreshed_record = sync_plan_metadata_to_job_record(
        runtime_context.JOBS_DB_PATH,
        job_id,
        updated_state,
    ) or record
    request_payload = dict(
        refreshed_record.get("request", {})
        if isinstance(refreshed_record.get("request"), dict)
        else {}
    )
    request_payload["workflow_mode"] = normalize_workflow_mode(
        request_payload.get("workflow_mode") or updated_state.get("job_meta", {}).get("workflow_mode")
    )
    update_job_record(
        runtime_context.JOBS_DB_PATH,
        job_id,
        stop_requested=False,
        status="queued",
        current_stage="planning",
        request=request_payload,
    )
    clear_job_stop_request(job_dir, job_id)

    refreshed_record = get_job_record(runtime_context.JOBS_DB_PATH, job_id) or refreshed_record
    try:
        submit_existing_job_pipeline(refreshed_record, request_payload=request_payload)
    except ValueError as exc:
        return api_error(exc)

    state = load_job_state(job_id, job_dir) or updated_state
    return jsonify(state)
