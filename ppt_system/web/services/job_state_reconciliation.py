from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ppt_system.jobs.active_job_registry import is_job_managed
from ppt_system.jobs.job_status_messages import INTERRUPTED_MESSAGE
from ppt_system.jobs.job_store import get_job as get_job_record
from ppt_system.jobs.job_store import update_job as update_job_record
from ppt_system.runtime import runtime_context
from ppt_system.runtime.time_utils import utc_now_naive
from ppt_system.web.services.app_config_runtime import read_config
from ppt_system.web.services.job_state_model import (
    DEFAULT_STALE_STOPPING_GRACE_SECONDS,
    NON_TERMINAL_JOB_STATUSES,
    STAGE_TERMINAL_STATUSES,
    find_terminal_stage_for_runtime_status,
    mark_state_interrupted,
    reconcile_job_runtime_status,
)
from ppt_system.web.services.job_state_store import cache_job_state, status_file
from ppt_system.web.services.job_state_transitions import finalize_job_interrupted

def reconcile_stale_stopping_job(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if not is_stale_stopping_job(record):
        return record
    assert record is not None
    job_id = str(record.get("job_id") or "").strip()
    job_dir = Path(str(record.get("job_dir") or ""))
    stage_key = str(record.get("current_stage") or "queued").strip() or "queued"
    message = INTERRUPTED_MESSAGE
    target = status_file(job_dir)

    if target.exists():
        finalize_job_interrupted(job_dir, job_id, stage_key, message)
    else:
        state = record.get("state", {})
        if not isinstance(state, dict):
            state = {}
        state = json.loads(json.dumps(state, ensure_ascii=False))
        state.setdefault("job_id", job_id)
        state.setdefault("stages", [])
        mark_state_interrupted(state, stage_key, message)
        job_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        cache_job_state(job_id, state)
        update_job_record(
            runtime_context.JOBS_DB_PATH,
            job_id,
            status="interrupted",
            current_stage=stage_key,
            state=state,
            stop_requested=False,
        )

    return get_job_record(runtime_context.JOBS_DB_PATH, job_id) or record

def reconcile_job_record(record: dict[str, Any] | None) -> dict[str, Any] | None:
    record = reconcile_stale_stopping_job(record)
    return reconcile_unmanaged_terminal_stage_job(record)

def reconcile_unmanaged_terminal_stage_job(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if not should_reconcile_unmanaged_terminal_stage_job(record):
        return record
    assert record is not None
    job_id = str(record.get("job_id") or "").strip()
    job_dir = Path(str(record.get("job_dir") or ""))
    state = load_state_for_record_reconciliation(record, job_dir)
    if not state:
        return record

    reconciled = reconcile_job_runtime_status(state)
    if str(reconciled.get("status") or "").strip() not in STAGE_TERMINAL_STATUSES:
        return record

    job_dir.mkdir(parents=True, exist_ok=True)
    status_file(job_dir).write_text(json.dumps(reconciled, ensure_ascii=False, indent=2), encoding="utf-8")
    cache_job_state(job_id, reconciled)
    update_job_record(
        runtime_context.JOBS_DB_PATH,
        job_id,
        status=reconciled.get("status", "interrupted"),
        current_stage=reconciled.get("current_stage", record.get("current_stage", "")),
        state=reconciled,
        stop_requested=False,
    )
    return get_job_record(runtime_context.JOBS_DB_PATH, job_id) or record

def should_reconcile_unmanaged_terminal_stage_job(record: dict[str, Any] | None) -> bool:
    if not record or str(record.get("status") or "").strip() not in NON_TERMINAL_JOB_STATUSES:
        return False
    job_id = str(record.get("job_id") or "").strip()
    if not job_id or is_job_managed(job_id):
        return False
    state = load_state_for_record_reconciliation(record, Path(str(record.get("job_dir") or "")))
    return bool(state and find_terminal_stage_for_runtime_status(state) is not None)

def load_state_for_record_reconciliation(record: dict[str, Any], job_dir: Path) -> dict[str, Any]:
    target = status_file(job_dir)
    if target.exists():
        try:
            state = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(state, dict):
                return state
        except (OSError, json.JSONDecodeError):
            pass
    state = record.get("state", {})
    return json.loads(json.dumps(state, ensure_ascii=False)) if isinstance(state, dict) else {}

def is_stale_stopping_job(record: dict[str, Any] | None) -> bool:
    if not record or str(record.get("status") or "").strip() != "stopping":
        return False
    job_id = str(record.get("job_id") or "").strip()
    if not job_id or is_job_managed(job_id):
        return False
    updated_at = parse_job_timestamp(record.get("updated_at"))
    if updated_at is None:
        return True
    return utc_now_naive() - updated_at >= timedelta(seconds=resolve_stale_stopping_grace_seconds())

def resolve_stale_stopping_grace_seconds() -> int:
    try:
        config = read_config()
    except Exception:
        config = {}
    raw_value = config.get("stopping_grace_seconds", DEFAULT_STALE_STOPPING_GRACE_SECONDS)
    try:
        return max(1, int(raw_value))
    except (TypeError, ValueError):
        return DEFAULT_STALE_STOPPING_GRACE_SECONDS

def parse_job_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for date_format in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, date_format)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed
