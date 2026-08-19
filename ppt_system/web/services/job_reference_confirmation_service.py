from __future__ import annotations

from pathlib import Path

from flask import jsonify

from ppt_system.jobs.job_store import get_job, update_job
from ppt_system.runtime import runtime_context
from ppt_system.web.services.api_response import api_error
from ppt_system.web.services.job_state_store import load_job_state, mutate_job_state
from ppt_system.web.services.job_submission_runtime import submit_existing_job_pipeline
from ppt_system.web.services.workflow_policy import AWAITING_REFERENCE_CONFIRMATION_STATUS, mark_reference_confirmed


def api_confirm_reference_pages(job_id: str):
    record = get_job(runtime_context.JOBS_DB_PATH, job_id)
    if not record:
        return api_error("任务不存在", 404)
    if str(record.get("status", "")) != AWAITING_REFERENCE_CONFIRMATION_STATUS:
        return api_error("当前任务不在原稿图确认阶段。", 409)
    job_dir = Path(record["job_dir"])

    def updater(state):
        references = state.get("reference_pages", [])
        pages = state.get("pages", [])
        if not pages or len(references) < len(pages):
            raise ValueError("原稿图尚未全部生成，暂时不能继续。")
        mark_reference_confirmed(state)
        state["status"] = "queued"
        state["current_stage"] = "elements_generation"
        state["error"] = ""
        state["stop_requested"] = False

    try:
        updated = mutate_job_state(job_dir, job_id, updater)
    except ValueError as exc:
        return api_error(exc)
    update_job(runtime_context.JOBS_DB_PATH, job_id, status="queued", current_stage="elements_generation", stop_requested=False)
    refreshed = get_job(runtime_context.JOBS_DB_PATH, job_id) or record
    submit_existing_job_pipeline(refreshed, request_payload=dict(refreshed.get("request", {})))
    return jsonify(load_job_state(job_id, job_dir) or updated)
