from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import jsonify, request

from ppt_system.jobs.active_job_registry import is_job_managed
from ppt_system.jobs.job_delivery_state import attach_delivery_actions
from ppt_system.jobs.job_interrupt_signal import clear_job_stop_request, has_job_stop_request, request_job_stop
from ppt_system.jobs.job_status_messages import INTERRUPTED_MESSAGE
from ppt_system.jobs.job_store import current_timestamp as current_job_timestamp
from ppt_system.jobs.job_store import delete_job as delete_job_record
from ppt_system.jobs.job_store import get_job as get_job_record
from ppt_system.jobs.job_store import update_job as update_job_record
from ppt_system.jobs.job_targets import JOB_TARGET_EDITABLE_PPT, can_upgrade_to_editable
from ppt_system.runtime import runtime_context
from ppt_system.web.services.api_response import api_error, api_ok
from ppt_system.web.services.job_event_bus import JOB_EVENT_BUS
from ppt_system.web.services.job_state_model import prepare_state_for_resume
from ppt_system.web.services.job_state_reconciliation import reconcile_job_record
from ppt_system.web.services.job_state_store import load_job_state, mutate_job_state
from ppt_system.web.services.job_state_transitions import finalize_job_interrupted, reconcile_resume_state
from ppt_system.web.services.job_state_view import (
    attach_resume_control,
    enrich_job_state_with_record,
    job_summary,
    remove_job_artifacts,
)
from ppt_system.web.services.job_submission_runtime import submit_existing_job_pipeline

def api_delete_job(job_id: str):
    record = get_job_record(runtime_context.JOBS_DB_PATH, job_id)
    record = reconcile_job_record(record)
    if not record:
        return api_error("任务不存在", 404)
    if record["status"] in {"queued", "running", "stopping"}:
        return api_error("运行中任务不能删除，请先暂停任务后再删除。")
    remove_job_artifacts(Path(record["job_dir"]))
    delete_job_record(runtime_context.JOBS_DB_PATH, job_id)
    with runtime_context.JOB_STATUS_LOCK:
        runtime_context.JOB_STATUS_CACHE.pop(job_id, None)
    JOB_EVENT_BUS.notify_job_changed(job_id)
    return api_ok()

def api_update_job(job_id: str):
    record = get_job_record(runtime_context.JOBS_DB_PATH, job_id)
    record = reconcile_job_record(record)
    if not record:
        return api_error("任务不存在", 404)

    payload = request.get_json(silent=True) or {}
    fields: dict[str, Any] = {}
    action = str(payload.get("action", "")).strip().lower()

    if "title" in payload:
        title = str(payload.get("title") or "").strip()
        if not title:
            return api_error("任务名称不能为空。")
        fields["title"] = title

    touch_updated_at = True
    if action == "pin":
        fields["pinned_at"] = current_job_timestamp()
        touch_updated_at = False
    elif action == "unpin":
        fields["pinned_at"] = ""
        touch_updated_at = False
    elif action and action != "rename":
        return api_error(f"不支持的任务操作：{action}")

    if not fields:
        return api_error("没有可更新的任务字段。")

    update_job_record(runtime_context.JOBS_DB_PATH, job_id, touch_updated_at=touch_updated_at, **fields)
    refreshed = get_job_record(runtime_context.JOBS_DB_PATH, job_id)
    if not refreshed:
        return api_error("任务不存在", 404)
    return jsonify(job_summary(refreshed))

def api_interrupt_job(job_id: str):
    record = get_job_record(runtime_context.JOBS_DB_PATH, job_id)
    record = reconcile_job_record(record)
    if not record:
        return api_error("任务不存在", 404)
    if record["status"] not in {"queued", "running"}:
        return api_error("只有运行中任务可以中断。")
    current_stage = str(record.get("current_stage") or "queued")
    job_dir = Path(record["job_dir"])
    request_job_stop(job_dir, job_id)
    updated_state = finalize_job_interrupted(job_dir, job_id, current_stage, INTERRUPTED_MESSAGE)
    update_job_record(
        runtime_context.JOBS_DB_PATH,
        job_id,
        stop_requested=False,
        status="interrupted",
        current_stage=current_stage,
        state=updated_state,
    )
    refreshed_record = get_job_record(runtime_context.JOBS_DB_PATH, job_id) or record
    response_state = enrich_job_state_with_record(updated_state, refreshed_record)
    response_state = attach_delivery_actions(response_state, job_dir)
    attach_resume_control(response_state, refreshed_record, job_dir)
    return jsonify(response_state)

def api_resume_job(job_id: str):
    record = get_job_record(runtime_context.JOBS_DB_PATH, job_id)
    record = reconcile_job_record(record)
    if not record:
        return api_error("任务不存在", 404)
    current_state = record.get("state", {})
    can_resume = record["status"] in {"interrupted", "error"} or can_upgrade_to_editable(current_state)
    if not can_resume:
        return api_error("当前任务状态不支持继续。")
    request_payload = record.get("request", {})
    next_job_target = JOB_TARGET_EDITABLE_PPT
    request_payload["job_target"] = next_job_target
    job_dir = Path(record["job_dir"])
    if is_job_managed(job_id) and has_job_stop_request(job_dir, job_id):
        return api_error("任务后台正在停止，请稍后再继续。")
    update_job_record(
        runtime_context.JOBS_DB_PATH,
        job_id,
        stop_requested=False,
        status="queued",
        request=request_payload,
    )
    clear_job_stop_request(job_dir, job_id)

    mutate_job_state(
        job_dir,
        job_id,
        lambda state: prepare_state_for_resume(state, next_job_target),
    )
    reconcile_resume_state(job_dir, job_id)
    try:
        submit_existing_job_pipeline(record, request_payload=request_payload)
    except ValueError as exc:
        return api_error(exc)
    state = load_job_state(job_id, job_dir)
    if state:
        refreshed_record = get_job_record(runtime_context.JOBS_DB_PATH, job_id) or record
        response_state = attach_delivery_actions(
            enrich_job_state_with_record(state, refreshed_record),
            job_dir,
        )
        attach_resume_control(response_state, refreshed_record, job_dir)
        return jsonify(response_state)
    return api_ok()
