from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import time
import traceback
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, render_template, request, send_from_directory, stream_with_context

from ppt_system.generation.content_agent import build_content_plan
from ppt_system.export.delivery_options import (
    EDITABLE_PPT_DELIVERY_KEY,
    EDITABLE_SINGLE_PAGE_DELIVERY_ACTION_KEY,
    EDITABLE_SPLIT_PAGES_DELIVERY_ACTION_KEY,
    REFERENCE_PPT_DELIVERY_KEY,
    REFERENCE_PPT_FILENAME,
    build_editable_ppt_filename,
    normalize_editable_delivery_layer_mode,
)
from ppt_system.export.export_layer_mode import OVERLAY_LAYER_MODE, SEPARATE_LAYER_MODE
from ppt_system.export.export_pipeline import export_editable_delivery, export_web_job_to_pptx
from ppt_system.generation.generation_options import default_generation_options, resolve_generation_options
from ppt_system.generation.generation_prompts import build_elements_prompt
from ppt_system.jobs.active_job_registry import bind_job_future, is_job_managed, mark_job_managed
from ppt_system.jobs.job_delivery_state import (
    attach_delivery_actions,
    build_editable_delivery_payload,
    build_reference_delivery_payload,
    get_editable_delivery_bundle,
    merge_job_result,
    normalize_job_result_payload,
    set_editable_delivery,
    set_editable_delivery_bundle,
    set_reference_delivery,
)
from ppt_system.generation.page_evaluator import evaluate_plan
from ppt_system.generation.page_richness import PAGE_RICHNESS_LEVELS
from ppt_system.jobs.job_store import create_job as create_job_record
from ppt_system.jobs.job_store import current_timestamp as current_job_timestamp
from ppt_system.jobs.job_store import delete_job as delete_job_record
from ppt_system.jobs.job_store import get_job as get_job_record
from ppt_system.jobs.job_store import init_db as init_job_db
from ppt_system.jobs.job_store import list_jobs as list_job_records
from ppt_system.jobs.job_store import update_job as update_job_record
from ppt_system.jobs.db_lifecycle import collect_db_stats as collect_job_db_stats
from ppt_system.jobs.db_lifecycle import delete_jobs_by_ids as delete_job_db_records
from ppt_system.jobs.db_lifecycle import list_cleanup_candidates as list_job_db_cleanup_candidates
from ppt_system.jobs.db_lifecycle import vacuum_db as vacuum_job_db
from ppt_system.jobs.db_maintenance_scheduler import JobDbMaintenanceScheduler
from ppt_system.jobs.db_maintenance_scheduler import resolve_job_db_maintenance_config
from ppt_system.jobs.job_status_messages import INTERRUPTED_MESSAGE, STOPPING_MESSAGE
from ppt_system.jobs.job_interrupt_signal import clear_job_stop_request, has_job_stop_request, request_job_stop
from ppt_system.jobs.job_targets import (
    JOB_TARGET_EDITABLE_PPT,
    TARGET_LABELS,
    build_completion_summary,
    can_upgrade_to_editable,
    get_terminal_stage,
    normalize_job_target,
    should_continue_after_stage,
)
from ppt_system.integrations.model_config import (
    delete_model_config,
    get_active_model_config,
    list_model_configs,
    read_config as read_json_config,
    save_model_env_fields,
    save_model_api_key,
    set_active_model_config,
    upsert_model_config,
    write_config,
    delete_model_env_fields,
    delete_model_api_key,
)
from ppt_system.integrations.openai_chat_provider import OpenAIChatProvider
from ppt_system.integrations.openai_image_provider import OpenAIImageProvider
from ppt_system.generation.page_image_pipeline import run_page_image_pipeline
from ppt_system.generation.planning_state import has_complete_planning_state
from ppt_system.export.reference_preview_export import export_reference_images_to_pptx
from ppt_system.export.stage_labels import normalize_stage_label
from ppt_system.export.stage_resume import has_expected_outputs, reconcile_completed_stages, should_run_stage
from ppt_system.web.services.app_config_runtime import (
    build_export_options,
    copy_style_reference_images,
    list_style_reference_images,
    read_config,
    resolve_image_preset,
)
from ppt_system.web.services.job_state_runtime import (
    _attach_page_evaluations,
    append_stage_log,
    attach_resume_control,
    build_job_state,
    build_job_title,
    cache_job_state,
    ensure_job_not_stopped,
    enrich_job_state_with_record,
    extract_element_pages_from_state,
    extract_pages_from_state,
    extract_reference_pages_from_state,
    finalize_job_completed,
    finalize_job_error,
    finalize_job_interrupted,
    get_job_state_snapshot,
    get_job_target_from_state,
    job_summary,
    list_job_summaries,
    load_job_state,
    mark_job_stopping,
    mutate_job_state,
    normalize_job_state_labels,
    prepare_state_for_resume,
    reconcile_job_record,
    reconcile_stale_stopping_job,
    reconcile_resume_state,
    remove_job_artifacts,
    save_job_state,
    should_stop_job,
    status_file,
    sync_job_record,
    update_page_state,
    update_stage,
    write_error,
)
from ppt_system.jobs.job_errors import JobInterruptedError
from ppt_system.web.services.job_pipeline_runner import run_job_pipeline
from ppt_system.web.services.job_image_tasks import submit_elements_task, submit_reference_task
from ppt_system.web.services.job_snapshot_runtime import (
    build_job_payload,
    build_job_payload_from_state,
    load_job_snapshot,
    write_job_snapshot,
)
from ppt_system.web.services.job_db_maintenance_service import execute_job_db_maintenance
from ppt_system.web.services.job_runtime_limits import (
    BoundedJobStatusCache,
    resolve_job_status_cache_max_items,
    resolve_job_worker_count,
)
from ppt_system.web.services.plan_version_store import (
    apply_plan_to_state,
    build_plan_response,
    get_active_plan_payload,
    get_active_plan_version,
    save_plan_version,
)
from ppt_system.web.services.workflow_policy import (
    AWAITING_PLAN_CONFIRMATION_STATUS,
    build_confirmation_policy,
    ensure_workflow_metadata,
    get_workflow_mode_label,
    initial_plan_confirmation_state,
    is_plan_confirmed,
    mark_awaiting_plan_confirmation,
    mark_plan_confirmed,
    mark_plan_draft,
    normalize_workflow_mode,
    requires_plan_confirmation,
    should_pause_after_planning,
)
from ppt_system.web.services.static_assets import build_static_asset_version
from ppt_system.runtime.app_paths import (
    ensure_runtime_directories,
    resolve_application_root,
    resolve_configured_job_dir,
    resolve_configured_output_root,
    resolve_runtime_paths,
)


sys.modules.setdefault("main", sys.modules[__name__])

ROOT = resolve_application_root(__file__)
RUNTIME_PATHS = resolve_runtime_paths(ROOT)
ensure_runtime_directories(RUNTIME_PATHS)
DATA_DIR = RUNTIME_PATHS.data_dir
CONFIG_PATH = RUNTIME_PATHS.config_path
LOCAL_CONFIG_PATH = RUNTIME_PATHS.local_config_path
ENV_PATH = RUNTIME_PATHS.env_path
OUTPUT_ROOT = RUNTIME_PATHS.default_output_dir
LOGS_DIR = RUNTIME_PATHS.logs_dir
JOBS_DB_PATH = OUTPUT_ROOT / "jobs.sqlite3"
init_job_db(JOBS_DB_PATH)
JOB_EXECUTOR = ThreadPoolExecutor(max_workers=resolve_job_worker_count(read_config))
JOB_STATUS_LOCK = threading.Lock()
JOB_STATUS_CACHE: BoundedJobStatusCache = BoundedJobStatusCache(
    max_items=resolve_job_status_cache_max_items(read_config)
)
JOB_DB_MAINTENANCE_SCHEDULER = JobDbMaintenanceScheduler(
    db_path=JOBS_DB_PATH,
    config_loader=read_config,
    maintenance_runner=execute_job_db_maintenance,
    stats_collector=collect_job_db_stats,
    running_jobs_counter=lambda: sum(
        1
        for job in list_job_summaries(limit=None)
        if str(job.get("status") or "").strip() in {"queued", "running", "stopping"}
    ),
)
JOB_DB_MAINTENANCE_SCHEDULER.start()


from ppt_system.web import create_app


def static_asset_version() -> str:
    return build_static_asset_version(ROOT)


app = create_app(
    ROOT,
    static_asset_version_provider=static_asset_version,
)


def should_open_browser() -> bool:
    return str(os.environ.get("PPT_SYSTEM_NO_BROWSER", "")).strip().lower() not in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    if should_open_browser():
        threading.Timer(1.0, lambda: webbrowser.open("http://127.0.0.1:7860")).start()
    app.run(host="127.0.0.1", port=7860, debug=False)
