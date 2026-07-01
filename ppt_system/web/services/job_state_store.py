from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from ppt_system.jobs.job_delivery_state import merge_job_result
from ppt_system.jobs.job_store import get_job as get_job_record
from ppt_system.jobs.job_store import update_job as update_job_record
from ppt_system.runtime import runtime_context
from ppt_system.web.services.job_event_bus import JOB_EVENT_BUS

def write_error(job_dir: Path, payload: dict[str, Any]) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "error.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

def status_file(job_dir: Path) -> Path:
    return job_dir / "status.json"

def cache_job_state(job_id: str, state: dict[str, Any]) -> None:
    with runtime_context.JOB_STATUS_LOCK:
        runtime_context.JOB_STATUS_CACHE[job_id] = state

def save_job_state(job_dir: Path, state: dict[str, Any]) -> None:
    cache_job_state(state["job_id"], state)
    status_file(job_dir).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    sync_job_record(state["job_id"], state)
    JOB_EVENT_BUS.notify_job_changed(state["job_id"])

def load_job_state(job_id: str, job_dir: Path) -> dict[str, Any] | None:
    with runtime_context.JOB_STATUS_LOCK:
        cached = runtime_context.JOB_STATUS_CACHE.get(job_id)
    if cached:
        return cached
    target = status_file(job_dir)
    if not target.exists():
        return None
    state = json.loads(target.read_text(encoding="utf-8"))
    cache_job_state(job_id, state)
    return state

def mutate_job_state(job_dir: Path, job_id: str, updater: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    with runtime_context.JOB_STATUS_LOCK:
        current = runtime_context.JOB_STATUS_CACHE.get(job_id)
        if current is None:
            target = status_file(job_dir)
            if target.exists():
                current = json.loads(target.read_text(encoding="utf-8"))
            else:
                raise RuntimeError(f"找不到任务状态：{job_id}")
        state = json.loads(json.dumps(current, ensure_ascii=False))
        updater(state)
        runtime_context.JOB_STATUS_CACHE[job_id] = state
        status_file(job_dir).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        sync_job_record(job_id, state)
    JOB_EVENT_BUS.notify_job_changed(job_id)
    return state

def sync_job_record(job_id: str, state: dict[str, Any]) -> None:
    record = get_job_record(runtime_context.JOBS_DB_PATH, job_id)
    if not record:
        return
    merged_result = merge_job_result(record.get("result", {}), state.get("result", {}))
    update_job_record(
        runtime_context.JOBS_DB_PATH,
        job_id,
        status=state.get("status", "queued"),
        current_stage=state.get("current_stage", "queued"),
        state=state,
        result=merged_result,
        stop_requested=state.get("stop_requested", False),
    )
    JOB_EVENT_BUS.notify_history_changed()
