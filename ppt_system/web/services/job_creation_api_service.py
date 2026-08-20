from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from flask import jsonify, request

from ppt_system.jobs.active_job_registry import mark_job_managed
from ppt_system.jobs.job_delivery_state import attach_delivery_actions
from ppt_system.jobs.job_store import create_job as create_job_record
from ppt_system.jobs.job_store import get_job as get_job_record
from ppt_system.jobs.job_targets import JOB_TARGET_EDITABLE_PPT, JOB_TARGET_REFERENCE_ONLY, normalize_job_target
from ppt_system.generation.generation_options import resolve_generation_options
from ppt_system.runtime import runtime_context
from ppt_system.web.services.api_response import api_error
from ppt_system.web.services.app_config_runtime import (
    copy_style_reference_images,
    list_style_reference_images,
    read_config,
    resolve_image_preset,
)
from ppt_system.web.services.external_reference_job import (
    EXTERNAL_REFERENCE_SOURCE_MODE,
    SUPPORTED_IMAGE_SUFFIXES,
    create_external_reference_job,
)
from ppt_system.web.services.job_api_common import _is_truthy, _parse_page_count, _resolve_job_dir
from ppt_system.web.services.job_pipeline_runner import run_job_pipeline
from ppt_system.web.services.job_state_model import build_job_state, build_job_title
from ppt_system.web.services.job_state_store import save_job_state
from ppt_system.web.services.job_submission_runtime import bind_submitted_job, build_active_config
from ppt_system.web.services.workflow_policy import normalize_workflow_mode

def api_create_job():
    config = read_config()
    source_mode = request.form.get("source_mode", "").strip().lower()
    if source_mode == EXTERNAL_REFERENCE_SOURCE_MODE:
        return _api_create_external_reference_job(config)

    content = request.form.get("content", "").strip()
    try:
        page_count = _parse_page_count(request.form.get("page_count"), config)
    except ValueError as exc:
        return api_error(exc)
    image_preset_name = request.form.get("image_preset", str(config.get("default_image_preset", "2k")))
    image_quality = request.form.get("image_quality", str(config.get("image_quality", "medium"))).strip().lower()
    job_target = normalize_job_target(
        request.form.get("job_target", JOB_TARGET_EDITABLE_PPT),
        JOB_TARGET_EDITABLE_PPT,
    )
    workflow_mode = normalize_workflow_mode(request.form.get("workflow_mode", "auto"))
    style_notes = request.form.get("style_notes", "").strip()
    reuse_style_refs_from_job_id = request.form.get("reuse_style_refs_from_job_id", "").strip()
    generation_payload = dict(request.form)
    raw_page_richness_map = request.form.get("page_richness_map", "").strip()
    if raw_page_richness_map:
        try:
            generation_payload["page_richness_map"] = json.loads(raw_page_richness_map)
        except json.JSONDecodeError:
            return api_error("逐页内容丰富度参数格式错误。")
    generation_options = resolve_generation_options(generation_payload, config=config)

    if not content:
        return api_error("请输入内容。")
    if page_count < 1 or page_count > int(config["max_pages"]):
        return api_error(f"页数必须在 1 到 {config['max_pages']} 之间。")

    try:
        image_preset = resolve_image_preset(config, image_preset_name)
    except ValueError as exc:
        return api_error(exc)

    image_width = int(image_preset["width"])
    image_height = int(image_preset["height"])
    if image_quality not in {"low", "medium", "high", "auto"}:
        return api_error("图像质量只能选择 low、medium、high 或 auto。")
    active_config = build_active_config(config, image_preset, image_quality)

    job_id = uuid.uuid4().hex[:12]
    job_dir = _resolve_job_dir(config, job_id)
    refs_dir = job_dir / "style_refs"
    stage1_dir = job_dir / "01_reference_pages"
    stage2_dir = job_dir / "02_elements_pages"
    refs_dir.mkdir(parents=True, exist_ok=True)
    stage1_dir.mkdir(parents=True, exist_ok=True)
    stage2_dir.mkdir(parents=True, exist_ok=True)

    uploaded_style_ref_count = 0
    for file in request.files.getlist("style_images"):
        if file and file.filename:
            target = refs_dir / Path(file.filename).name
            file.save(target)
            uploaded_style_ref_count += 1
    if uploaded_style_ref_count == 0 and reuse_style_refs_from_job_id:
        source_record = get_job_record(runtime_context.JOBS_DB_PATH, reuse_style_refs_from_job_id)
        if source_record:
            copy_style_reference_images(Path(source_record["job_dir"]), refs_dir)
    style_reference_images = list_style_reference_images(job_id, job_dir)
    state = build_job_state(
        job_id,
        content,
        page_count,
        image_preset,
        image_quality,
        style_notes,
        generation_options,
        style_reference_images,
        job_target,
        workflow_mode,
    )
    request_payload = {
        "content": content,
        "page_count": page_count,
        "image_preset": image_preset_name,
        "image_quality": image_quality,
        "style_notes": style_notes,
        "job_target": job_target,
        "workflow_mode": workflow_mode,
        "generation_options": generation_options,
        "include_cover_page": generation_options["include_cover_page"],
        "page_richness_default": generation_options["page_richness_default"],
        "page_richness_map": generation_options["page_richness_map"],
        "reference_style_adherence": generation_options["reference_style_adherence"],
        "theme_color": generation_options["theme_color"],
        "style_reference_images": style_reference_images,
    }
    create_job_record(
        runtime_context.JOBS_DB_PATH,
        {
            "job_id": job_id,
            "status": state["status"],
            "current_stage": state["current_stage"],
            "title": build_job_title(content),
            "content": content,
            "page_count": page_count,
            "image_preset": image_preset_name,
            "image_quality": image_quality,
            "style_notes": style_notes,
            "job_dir": str(job_dir),
            "request": request_payload,
            "state": state,
            "result": {},
            "stop_requested": False,
        },
    )
    save_job_state(job_dir, state)
    mark_job_managed(job_id)
    future = runtime_context.JOB_EXECUTOR.submit(
        run_job_pipeline,
        job_id,
        job_dir,
        config,
        active_config,
        content,
        page_count,
        image_preset,
        style_notes,
        generation_options,
        stage1_dir,
        stage2_dir,
        refs_dir,
    )
    bind_submitted_job(job_id, future)
    return jsonify(state), 202

def _api_create_external_reference_job(config: dict[str, Any]):
    files = [file for file in request.files.getlist("reference_images") if file and file.filename]
    if not files:
        return api_error("请上传至少一张原稿图。")
    max_pages = int(config.get("max_pages") or 0)
    if max_pages > 0 and len(files) > max_pages:
        return api_error(f"导入原稿图数量不能超过 {max_pages} 张。")

    job_id = uuid.uuid4().hex[:12]
    job_dir = _resolve_job_dir(config, job_id)
    upload_dir = job_dir / "external_reference_uploads"
    source_paths: list[Path] = []
    try:
        upload_dir.mkdir(parents=True, exist_ok=True)
        for index, file in enumerate(files, start=1):
            original_name = Path(file.filename).name or f"reference_{index:02d}.png"
            suffix = Path(original_name).suffix.lower()
            if suffix not in SUPPORTED_IMAGE_SUFFIXES:
                suffixes = "、".join(sorted(SUPPORTED_IMAGE_SUFFIXES))
                shutil.rmtree(job_dir, ignore_errors=True)
                return api_error(f"不支持的原稿图格式：{suffix or original_name}；支持格式：{suffixes}")
            target = upload_dir / f"{index:02d}_{original_name}"
            file.save(target)
            source_paths.append(target)

        image_preset_name = request.form.get("image_preset", str(config.get("default_image_preset", "2k")))
        image_quality = request.form.get("image_quality", str(config.get("image_quality", "medium"))).strip().lower()
        create_only = (
            _is_truthy(request.form.get("external_reference_create_only"))
            or request.form.get("job_target", "").strip().lower() == JOB_TARGET_REFERENCE_ONLY
        )
        created = create_external_reference_job(
            config=config,
            source_images=source_paths,
            job_id=job_id,
            title=request.form.get("title", "").strip(),
            content=request.form.get("content", "").strip(),
            page_title=request.form.get("page_title", "").strip(),
            image_preset_name=image_preset_name,
            image_quality=image_quality,
            resize_mode=request.form.get("external_reference_resize_mode", "stretch"),
            background=request.form.get("external_reference_background", "#FFFFFF"),
            create_only=create_only,
        )
    except ValueError as exc:
        if not get_job_record(runtime_context.JOBS_DB_PATH, job_id) and job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)
        return api_error(exc)
    except Exception as exc:
        if not get_job_record(runtime_context.JOBS_DB_PATH, job_id) and job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)
        return api_error(exc, 500)

    state = created["state"]
    if not create_only:
        mark_job_managed(job_id)
        future = runtime_context.JOB_EXECUTOR.submit(
            run_job_pipeline,
            job_id,
            created["job_dir"],
            config,
            created["active_config"],
            created["content"],
            created["page_count"],
            created["image_preset"],
            "",
            created["generation_options"],
            created["stage1_dir"],
            created["stage2_dir"],
            created["refs_dir"],
        )
        bind_submitted_job(job_id, future)

    return jsonify(attach_delivery_actions(state, Path(created["job_dir"]))), 202
