from __future__ import annotations

from pathlib import Path
from typing import Any

from ppt_system.jobs.job_store import get_job as get_job_record
from ppt_system.runtime import runtime_context
from ppt_system.runtime.app_paths import resolve_configured_job_dir
from ppt_system.web.services.job_state_reconciliation import reconcile_job_record
from ppt_system.web.services.job_state_store import load_job_state

def _resolve_job_dir(config: dict[str, Any], job_id: str) -> Path:
    return resolve_configured_job_dir(runtime_context.RUNTIME_PATHS, config, job_id)

def _is_truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

def _parse_page_count(raw_value: Any, config: dict[str, Any]) -> int:
    value = config.get("default_pages") if raw_value is None or str(raw_value).strip() == "" else raw_value
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError("页数必须是整数。") from None

def _get_existing_job_record(job_id: str) -> dict[str, Any] | None:
    record = get_job_record(runtime_context.JOBS_DB_PATH, job_id)
    return reconcile_job_record(record)

def _load_editable_job_state(record: dict[str, Any], job_dir: Path) -> dict[str, Any]:
    state = load_job_state(str(record["job_id"]), job_dir)
    if isinstance(state, dict) and state:
        return state
    record_state = record.get("state", {})
    return record_state if isinstance(record_state, dict) else {}

def _set_stage_status(
    state: dict[str, Any],
    stage_key: str,
    *,
    status: str,
    summary: str,
) -> None:
    stages = state.get("stages", [])
    if not isinstance(stages, list):
        return
    for stage in stages:
        if isinstance(stage, dict) and str(stage.get("key") or "") == stage_key:
            stage["status"] = status
            stage["summary"] = summary
            return
