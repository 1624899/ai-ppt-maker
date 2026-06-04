from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ppt_system.runtime.time_utils import utc_iso_timestamp


STOP_SIGNAL_FILE_NAME = ".job_stop_requested.json"


def job_stop_signal_path(job_dir: Path) -> Path:
    return Path(job_dir) / STOP_SIGNAL_FILE_NAME


def request_job_stop(job_dir: Path, job_id: str) -> None:
    target = job_stop_signal_path(job_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "job_id": str(job_id),
        "requested_at": utc_iso_timestamp(),
    }
    temp_path = target.with_suffix(target.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(target)


def has_job_stop_request(job_dir: Path, job_id: str | None = None) -> bool:
    target = job_stop_signal_path(job_dir)
    if not target.exists():
        return False
    expected_job_id = str(job_id or "").strip()
    if not expected_job_id:
        return True
    try:
        payload: Any = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    if not isinstance(payload, dict):
        return True
    signal_job_id = str(payload.get("job_id") or "").strip()
    return not signal_job_id or signal_job_id == expected_job_id


def clear_job_stop_request(job_dir: Path, job_id: str | None = None) -> None:
    if not has_job_stop_request(job_dir, job_id):
        return
    try:
        job_stop_signal_path(job_dir).unlink()
    except FileNotFoundError:
        pass
