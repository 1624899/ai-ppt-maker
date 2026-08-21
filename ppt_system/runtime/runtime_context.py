from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ppt_system.integrations.model_config import read_config as read_json_config
from ppt_system.jobs.db_lifecycle import collect_db_stats as collect_job_db_stats
from ppt_system.jobs.db_maintenance_scheduler import JobDbMaintenanceScheduler
from ppt_system.jobs.job_store import init_db as init_job_db, reconcile_job_directories
from ppt_system.runtime.app_paths import (
    ensure_runtime_directories,
    resolve_application_root,
    resolve_runtime_paths,
)
from ppt_system.runtime.file_logging import initialize_file_logging
from ppt_system.web.services.job_runtime_limits import (
    BoundedJobStatusCache,
    resolve_job_status_cache_max_items,
    resolve_job_worker_count,
)


ROOT = resolve_application_root(str(Path(__file__).resolve().parents[2] / "main.py"))
RUNTIME_PATHS = resolve_runtime_paths(ROOT)
ensure_runtime_directories(RUNTIME_PATHS)
LOG_PATH = initialize_file_logging(RUNTIME_PATHS.logs_dir)

DATA_DIR = RUNTIME_PATHS.data_dir
CONFIG_PATH = RUNTIME_PATHS.config_path
LOCAL_CONFIG_PATH = RUNTIME_PATHS.local_config_path
ENV_PATH = RUNTIME_PATHS.env_path
OUTPUT_ROOT = RUNTIME_PATHS.default_output_dir
LOGS_DIR = RUNTIME_PATHS.logs_dir
JOBS_DB_PATH = OUTPUT_ROOT / "jobs.sqlite3"

init_job_db(JOBS_DB_PATH)
reconcile_job_directories(JOBS_DB_PATH, OUTPUT_ROOT)


def read_config() -> dict[str, Any]:
    """读取合并后的运行时配置。"""
    return read_json_config(
        CONFIG_PATH,
        local_path=LOCAL_CONFIG_PATH,
        env_path=ENV_PATH,
    )


JOB_EXECUTOR = ThreadPoolExecutor(max_workers=resolve_job_worker_count(read_config))
JOB_STATUS_LOCK = threading.Lock()
JOB_STATUS_CACHE: BoundedJobStatusCache = BoundedJobStatusCache(
    max_items=resolve_job_status_cache_max_items(read_config)
)


def _run_job_db_maintenance(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from ppt_system.web.services.job_db_maintenance_service import execute_job_db_maintenance

    return execute_job_db_maintenance(*args, **kwargs)


def _count_running_jobs() -> int:
    from ppt_system.web.services.job_state_runtime import list_job_summaries

    return sum(
        1
        for job in list_job_summaries(limit=None)
        if str(job.get("status") or "").strip() in {"queued", "running", "stopping"}
    )


JOB_DB_MAINTENANCE_SCHEDULER = JobDbMaintenanceScheduler(
    db_path=JOBS_DB_PATH,
    config_loader=read_config,
    maintenance_runner=_run_job_db_maintenance,
    stats_collector=collect_job_db_stats,
    running_jobs_counter=_count_running_jobs,
)
JOB_DB_MAINTENANCE_SCHEDULER.start()
