from __future__ import annotations

from pathlib import Path
from typing import Any

from ppt_system.export.stage_resume import has_expected_outputs, reconcile_completed_stages
from ppt_system.generation.planning_state import has_complete_planning_state
from ppt_system.jobs.job_delivery_state import get_editable_delivery_bundle, normalize_job_result_payload
from ppt_system.jobs.job_errors import JobInterruptedError
from ppt_system.jobs.job_interrupt_signal import has_job_stop_request
from ppt_system.jobs.job_status_messages import STOPPING_MESSAGE
from ppt_system.jobs.job_store import get_job as get_job_record
from ppt_system.jobs.job_store import update_job as update_job_record
from ppt_system.jobs.job_targets import build_completion_summary, should_continue_after_stage
from ppt_system.runtime import runtime_context
from ppt_system.web.services.job_state_model import (
    extract_element_pages_from_state,
    extract_pages_from_state,
    extract_reference_pages_from_state,
    get_job_target_from_state,
    mark_state_interrupted,
)
from ppt_system.web.services.job_state_store import mutate_job_state, write_error

def append_stage_log(job_dir: Path, job_id: str, stage_key: str, message: str) -> None:
    def updater(state: dict[str, Any]) -> None:
        for stage in state["stages"]:
            if stage["key"] == stage_key:
                stage.setdefault("logs", []).append(message)
                break

    mutate_job_state(job_dir, job_id, updater)

def update_stage(
    job_dir: Path,
    job_id: str,
    stage_key: str,
    *,
    status: str | None = None,
    summary: str | None = None,
    data: dict[str, Any] | None = None,
    current_stage: str | None = None,
    job_status: str | None = None,
) -> None:
    def updater(state: dict[str, Any]) -> None:
        for stage in state["stages"]:
            if stage["key"] == stage_key:
                if status is not None:
                    stage["status"] = status
                if summary is not None:
                    stage["summary"] = summary
                if data is not None:
                    stage["data"] = data
                break
        if current_stage is not None:
            state["current_stage"] = current_stage
        if job_status is not None:
            state["status"] = job_status

    mutate_job_state(job_dir, job_id, updater)

def update_page_state(job_dir: Path, job_id: str, page_no: int, **fields: Any) -> None:
    def updater(state: dict[str, Any]) -> None:
        for page in state["pages"]:
            if int(page["page_no"]) == int(page_no):
                page.update(fields)
                break

    mutate_job_state(job_dir, job_id, updater)

def finalize_job_error(job_dir: Path, job_id: str, stage_key: str, payload: dict[str, Any]) -> None:
    def updater(state: dict[str, Any]) -> None:
        state["status"] = "error"
        state["current_stage"] = stage_key
        state["error"] = payload.get("error", "")
        state["stop_requested"] = False
        for stage in state["stages"]:
            if stage["key"] == stage_key:
                stage["status"] = "error"
                stage["summary"] = payload.get("error", "任务失败")
                stage.setdefault("logs", []).append(payload.get("error", "任务失败"))
                break

    mutate_job_state(job_dir, job_id, updater)
    write_error(job_dir, payload)

def finalize_job_interrupted(job_dir: Path, job_id: str, stage_key: str, message: str) -> dict[str, Any]:
    def updater(state: dict[str, Any]) -> None:
        mark_state_interrupted(state, stage_key, message)

    return mutate_job_state(job_dir, job_id, updater)

def mark_job_stopping(job_dir: Path, job_id: str, stage_key: str, message: str) -> None:
    record = get_job_record(runtime_context.JOBS_DB_PATH, job_id)
    if str((record or {}).get("status") or "").strip() == "interrupted":
        return

    def updater(state: dict[str, Any]) -> None:
        state["status"] = "stopping"
        state["current_stage"] = stage_key
        state["stop_requested"] = True
        for stage in state["stages"]:
            if stage["key"] == stage_key:
                stage["summary"] = message
                stage["status"] = "stopping"
                logs = stage.setdefault("logs", [])
                if message not in logs:
                    logs.append(message)
                break

    mutate_job_state(job_dir, job_id, updater)

def should_stop_job(job_id: str) -> bool:
    record = get_job_record(runtime_context.JOBS_DB_PATH, job_id)
    if bool(record and record.get("stop_requested")):
        return True
    if not record:
        return False
    return has_job_stop_request(Path(str(record.get("job_dir") or "")), job_id)

def ensure_job_not_stopped(job_dir: Path, job_id: str, stage_key: str) -> None:
    if should_stop_job(job_id):
        record = get_job_record(runtime_context.JOBS_DB_PATH, job_id) or {}
        if str(record.get("status") or "").strip() != "interrupted":
            mark_job_stopping(job_dir, job_id, stage_key, STOPPING_MESSAGE)
        raise JobInterruptedError(stage_key)

def finalize_job_completed(
    job_dir: Path,
    job_id: str,
    state: dict[str, Any],
    result_payload: dict[str, Any],
    *,
    terminal_stage: str,
    summary: str,
) -> None:
    job_target = get_job_target_from_state(state)
    normalized_result = normalize_job_result_payload(result_payload)
    deliveries = normalized_result.get("deliveries", {})

    def updater(current_state: dict[str, Any]) -> None:
        current_state["status"] = "completed"
        current_state["current_stage"] = terminal_stage
        current_state["result"] = normalized_result
        current_state["stop_requested"] = False
        current_state["error"] = ""

    mutate_job_state(job_dir, job_id, updater)
    update_stage(
        job_dir,
        job_id,
        terminal_stage,
        status="completed",
        summary=summary,
        data=deliveries if isinstance(deliveries, dict) else {},
        current_stage=terminal_stage,
        job_status="completed",
    )
    append_stage_log(job_dir, job_id, terminal_stage, build_completion_summary(job_target))
    update_job_record(
        runtime_context.JOBS_DB_PATH,
        job_id,
        stop_requested=False,
        status="completed",
        current_stage=terminal_stage,
        result=normalized_result,
    )

def reconcile_resume_state(job_dir: Path, job_id: str) -> dict[str, Any]:
    def updater(state: dict[str, Any]) -> None:
        pages = extract_pages_from_state(state)
        references = extract_reference_pages_from_state(state)
        elements = extract_element_pages_from_state(state)
        job_target = get_job_target_from_state(state)
        completion_map = {
            "planning": has_complete_planning_state(state),
            "reference_generation": has_expected_outputs(references, len(pages)),
            "elements_generation": has_expected_outputs(elements, len(references)),
            "ppt_export": bool(get_editable_delivery_bundle(state.get("result", {}))),
        }
        reconcile_completed_stages(state, completion_map)
        if not should_continue_after_stage(job_target, "reference_generation"):
            for stage in state.get("stages", []):
                if stage.get("key") in {"elements_generation", "ppt_export"} and stage.get("status") == "pending":
                    stage["status"] = "skipped"
                    stage["summary"] = "当前输出模式截至原稿图阶段，此阶段已跳过"

    return mutate_job_state(job_dir, job_id, updater)
