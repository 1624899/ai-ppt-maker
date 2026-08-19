from __future__ import annotations

from pathlib import Path
from typing import Any

from ppt_system.generation.generation_options import resolve_generation_options
from ppt_system.jobs.active_job_registry import bind_job_future, mark_job_managed, release_job_management
from ppt_system.runtime import runtime_context
from ppt_system.web.services.app_config_runtime import read_config, resolve_image_preset
from ppt_system.web.services.job_plan_record_sync import resolve_current_style_notes
from ppt_system.web.services.job_pipeline_runner import run_job_pipeline


def bind_submitted_job(job_id: str, submitted: object) -> None:
    if submitted is None:
        # 测试替身或同步执行器不会返回 Future，这时不要把任务长期标记为运行中托管。
        release_job_management(job_id)
        return
    if hasattr(submitted, "add_done_callback"):
        bind_job_future(job_id, submitted)


def build_active_config(
    config: dict[str, Any],
    image_preset: dict[str, Any],
    image_quality: str,
) -> dict[str, Any]:
    active_config = dict(config)
    active_config["image_width"] = int(image_preset["width"])
    active_config["image_height"] = int(image_preset["height"])
    active_config["active_image_size"] = str(image_preset["size"])
    active_config["active_image_resolution"] = str(image_preset["resolution"])
    active_config["image_quality"] = str(image_quality)
    return active_config


def submit_existing_job_pipeline(
    record: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
    request_payload: dict[str, Any] | None = None,
) -> object:
    active_config_source = config or read_config()
    payload = dict(request_payload or record.get("request", {}))
    state = record.get("state", {}) if isinstance(record.get("state"), dict) else {}
    job_meta = state.get("job_meta", {}) if isinstance(state.get("job_meta"), dict) else {}
    current_style_notes = resolve_current_style_notes(state, record)
    current_page_count = int(job_meta.get("page_count") or record.get("page_count") or 1)
    payload["style_notes"] = current_style_notes
    payload["page_count"] = current_page_count
    generation_options = resolve_generation_options(
        payload.get("generation_options", payload),
        config=active_config_source,
    )
    image_preset = resolve_image_preset(
        active_config_source,
        str(payload.get("image_preset", active_config_source["default_image_preset"])),
    )
    image_quality = str(payload.get("image_quality", record.get("image_quality") or active_config_source.get("image_quality", "medium")))
    active_config = build_active_config(active_config_source, image_preset, image_quality)
    job_id = str(record["job_id"])
    job_dir = Path(record["job_dir"])
    refs_dir = job_dir / "style_refs"
    stage1_dir = job_dir / "01_reference_pages"
    stage2_dir = job_dir / "02_elements_pages"
    refs_dir.mkdir(parents=True, exist_ok=True)
    stage1_dir.mkdir(parents=True, exist_ok=True)
    stage2_dir.mkdir(parents=True, exist_ok=True)

    mark_job_managed(job_id)
    submitted = runtime_context.JOB_EXECUTOR.submit(
        run_job_pipeline,
        job_id,
        job_dir,
        active_config_source,
        active_config,
        str(payload.get("content", record.get("content", ""))),
        current_page_count,
        image_preset,
        current_style_notes,
        generation_options,
        stage1_dir,
        stage2_dir,
        refs_dir,
    )
    bind_submitted_job(job_id, submitted)
    return submitted
