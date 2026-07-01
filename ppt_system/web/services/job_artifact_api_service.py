from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import send_from_directory

from ppt_system.jobs.job_store import get_job as get_job_record
from ppt_system.runtime import runtime_context
from ppt_system.web.services.app_config_runtime import read_config
from ppt_system.web.services.job_api_common import _resolve_job_dir

def serve_run_file(job_id: str, filename: str):
    record = get_job_record(runtime_context.JOBS_DB_PATH, job_id)
    directory = Path(record["job_dir"]) if record and record.get("job_dir") else _resolve_job_dir(read_config(), job_id)
    return send_from_directory(directory, filename)
