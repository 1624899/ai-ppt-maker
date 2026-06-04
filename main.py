from __future__ import annotations

import json
import shutil
import sys
import threading
import time
import traceback
import uuid
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
    save_model_api_key,
    set_active_model_config,
    upsert_model_config,
    write_config,
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
from ppt_system.web.services.job_pipeline_runner import run_job_pipeline
from ppt_system.web.services.job_db_maintenance_service import execute_job_db_maintenance
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


sys.modules.setdefault("main", sys.modules[__name__])

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
ENV_PATH = ROOT / ".env"
JOBS_DB_PATH = ROOT / "output" / "jobs.sqlite3"
init_job_db(JOBS_DB_PATH)
JOB_EXECUTOR = ThreadPoolExecutor(max_workers=2)
JOB_STATUS_LOCK = threading.Lock()
JOB_STATUS_CACHE: dict[str, dict[str, Any]] = {}
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


class JobInterruptedError(RuntimeError):
    pass


def build_job_payload(
    *,
    job_id: str,
    config: dict[str, Any],
    content: str,
    plan: dict[str, Any],
    pages: list[dict[str, Any]],
    references: list[dict[str, Any]],
    element_pages: list[dict[str, Any]],
    chat_provider: OpenAIChatProvider,
    chat_profile: dict[str, Any],
    image_provider: OpenAIImageProvider,
    image_profile: dict[str, Any],
    result_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "mode": config["generation_mode"],
        "content": content,
        "plan": plan,
        "pages": pages,
        "model_profiles": {
            "chat": {
                "id": chat_profile.get("id", ""),
                "name": chat_profile.get("name", ""),
                "model": chat_provider.model,
                "base_url": chat_provider.api_base_url,
            },
            "image": {
                "id": image_profile.get("id", ""),
                "name": image_profile.get("name", ""),
                "model": image_provider.model,
                "base_url": image_provider.api_base_url,
            },
        },
        "reference_pages": references,
        "element_pages": element_pages,
        "result": normalize_job_result_payload(result_payload),
    }


def write_job_snapshot(job_dir: Path, job_payload: dict[str, Any]) -> None:
    (job_dir / "job.json").write_text(
        json.dumps(job_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_job_snapshot(job_dir: Path) -> dict[str, Any]:
    snapshot_path = job_dir / "job.json"
    if not snapshot_path.exists():
        return {}
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_job_payload_from_state(
    state: dict[str, Any],
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result_payload = normalize_job_result_payload(state.get("result", {}))
    if isinstance(snapshot, dict) and snapshot:
        result_payload = merge_job_result(snapshot.get("result", {}), result_payload)
    source = snapshot if isinstance(snapshot, dict) and snapshot else {}
    return {
        "job_id": str(state.get("job_id") or source.get("job_id") or ""),
        "mode": str(source.get("mode") or ""),
        "content": str(source.get("content") or state.get("job_meta", {}).get("content") or ""),
        "plan": source.get("plan", state.get("plan", {})),
        "pages": source.get("pages", extract_pages_from_state(state)),
        "model_profiles": source.get("model_profiles", {}),
        "reference_pages": source.get("reference_pages", extract_reference_pages_from_state(state)),
        "element_pages": source.get("element_pages", extract_element_pages_from_state(state)),
        "result": result_payload,
    }


def submit_reference_task(
    executor: ThreadPoolExecutor,
    job_dir: Path,
    job_id: str,
    page: dict[str, Any],
    stage1_dir: Path,
    image_provider: OpenAIImageProvider,
    style_reference_paths: list[Path],
    reference_mode: str = "generation",
) -> tuple[Any, int, str, Path]:
    page_no = int(page["page_no"])
    prompt = str(page["image_prompt"]).strip()
    if not prompt:
        raise ValueError(f"第 {page_no} 页缺少原稿图提示词，需重新执行规划阶段")
    image_path = stage1_dir / f"page_{page_no:02d}_reference.png"
    prompt_path = stage1_dir / f"page_{page_no:02d}_reference_prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    update_page_state(job_dir, job_id, page_no, status="rendering_reference", reference_prompt=prompt)
    append_stage_log(job_dir, job_id, "reference_generation", f"第 {page_no} 页已进入原稿图生成队列")
    future = executor.submit(
        image_provider.generate_reference_page,
        prompt,
        image_path,
        style_reference_paths,
        reference_mode,
    )
    return future, page_no, prompt, image_path


def submit_elements_task(
    executor: ThreadPoolExecutor,
    job_dir: Path,
    job_id: str,
    page_no: int,
    elements_prompt: str,
    stage1_dir: Path,
    stage2_dir: Path,
    image_provider: OpenAIImageProvider,
) -> tuple[Any, int, Path]:
    ref_path = stage1_dir / f"page_{page_no:02d}_reference.png"
    out_path = stage2_dir / f"page_{page_no:02d}_elements.png"
    prompt_path = stage2_dir / f"page_{page_no:02d}_elements_prompt.txt"
    prompt_path.write_text(elements_prompt, encoding="utf-8")
    update_page_state(job_dir, job_id, page_no, status="rendering_elements", elements_prompt=elements_prompt)
    append_stage_log(job_dir, job_id, "elements_generation", f"第 {page_no} 页元素图已进入并发队列")
    future = executor.submit(image_provider.generate_elements_page, elements_prompt, ref_path, out_path)
    return future, page_no, out_path


from ppt_system.web import create_app


def static_asset_version() -> str:
    return "1"


app = create_app(
    ROOT,
    static_asset_version_provider=static_asset_version,
)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=7860, debug=False)
