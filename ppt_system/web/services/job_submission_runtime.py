from __future__ import annotations

from pathlib import Path
from typing import Any

from ppt_system.jobs.active_job_registry import release_job_management
from ppt_system.web.runtime import get_runtime_module


def bind_submitted_job(job_id: str, submitted: object) -> None:
    runtime = get_runtime_module()
    if submitted is None:
        # 测试替身或同步执行器不会返回 Future，这时不要把任务长期标记为运行中托管。
        release_job_management(job_id)
        return
    if hasattr(submitted, "add_done_callback"):
        runtime.bind_job_future(job_id, submitted)


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
    runtime = get_runtime_module()
    active_config_source = config or runtime.read_config()
    payload = dict(request_payload or record.get("request", {}))
    generation_options = runtime.resolve_generation_options(
        payload.get("generation_options", payload),
        config=active_config_source,
    )
    image_preset = runtime.resolve_image_preset(
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

    runtime.mark_job_managed(job_id)
    submitted = runtime.JOB_EXECUTOR.submit(
        runtime.run_job_pipeline,
        job_id,
        job_dir,
        active_config_source,
        active_config,
        str(payload.get("content", record.get("content", ""))),
        int(payload.get("page_count", record.get("page_count", 1))),
        image_preset,
        str(payload.get("style_notes", record.get("style_notes", ""))),
        generation_options,
        stage1_dir,
        stage2_dir,
        refs_dir,
    )
    bind_submitted_job(job_id, submitted)
    return submitted
