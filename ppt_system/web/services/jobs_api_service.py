from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from flask import Response, jsonify, request, send_from_directory, stream_with_context

from ppt_system.web.services.api_response import api_error, api_ok
from ppt_system.export.delivery_options import (
    EDITABLE_PPT_DELIVERY_KEY,
    REFERENCE_PPT_DELIVERY_KEY,
    REFERENCE_PPT_FILENAME,
    build_editable_ppt_filename,
    normalize_editable_delivery_layer_mode,
)
from ppt_system.export.editable_delivery_cache import (
    load_cached_editable_delivery,
    save_editable_delivery_cache,
)
from ppt_system.export.export_pipeline import export_editable_delivery
from ppt_system.export.reference_preview_export import export_reference_images_to_pptx
from ppt_system.generation.generation_options import resolve_generation_options
from ppt_system.generation.planning_state import has_complete_planning_state
from ppt_system.jobs.active_job_registry import is_job_managed, mark_job_managed
from ppt_system.jobs.job_delivery_state import (
    attach_delivery_actions,
    build_editable_delivery_payload,
    build_reference_delivery_payload,
    get_editable_delivery_bundle,
    normalize_job_result_payload,
    set_editable_delivery,
    set_reference_delivery,
)
from ppt_system.jobs.job_interrupt_signal import clear_job_stop_request, has_job_stop_request, request_job_stop
from ppt_system.jobs.job_status_messages import INTERRUPTED_MESSAGE
from ppt_system.jobs.job_store import create_job as create_job_record
from ppt_system.jobs.job_store import current_timestamp as current_job_timestamp
from ppt_system.jobs.job_store import delete_job as delete_job_record
from ppt_system.jobs.job_store import get_job as get_job_record
from ppt_system.jobs.job_store import update_job as update_job_record
from ppt_system.jobs.job_targets import (
    JOB_TARGET_EDITABLE_PPT,
    JOB_TARGET_REFERENCE_ONLY,
    can_upgrade_to_editable,
    normalize_job_target,
)
from ppt_system.runtime import runtime_context
from ppt_system.runtime.app_paths import resolve_configured_job_dir
from ppt_system.web.services.app_config_runtime import (
    copy_style_reference_images,
    list_style_reference_images,
    read_config,
    resolve_image_preset,
)
from ppt_system.web.services.job_pipeline_runner import run_job_pipeline
from ppt_system.web.services.job_submission_runtime import (
    bind_submitted_job,
    build_active_config,
    submit_existing_job_pipeline,
)
from ppt_system.web.services.job_event_bus import JOB_EVENT_BUS
from ppt_system.web.services.job_snapshot_runtime import (
    build_job_payload_from_state,
    load_job_snapshot,
    resolve_delivery_action_layer_mode,
    write_job_snapshot,
)
from ppt_system.web.services.external_reference_job import (
    EXTERNAL_REFERENCE_SOURCE_MODE,
    SUPPORTED_IMAGE_SUFFIXES,
    create_external_reference_job,
)
from ppt_system.web.services.job_state_runtime import (
    attach_resume_control,
    build_job_state,
    build_job_title,
    enrich_job_state_with_record,
    extract_reference_pages_from_state,
    finalize_job_interrupted,
    get_job_state_snapshot,
    job_summary,
    list_job_summaries,
    load_job_state,
    mutate_job_state,
    prepare_state_for_resume,
    reconcile_job_record,
    reconcile_resume_state,
    remove_job_artifacts,
    save_job_state,
)
from ppt_system.web.services.plan_version_store import (
    apply_plan_to_state,
    build_plan_response,
    get_active_plan_payload,
    save_plan_version,
)
from ppt_system.web.services.workflow_policy import (
    AWAITING_PLAN_CONFIRMATION_STATUS,
    ensure_workflow_metadata,
    mark_plan_confirmed,
    mark_plan_draft,
    normalize_workflow_mode,
)


def _resolve_job_dir(config: dict[str, Any], job_id: str) -> Path:
    return resolve_configured_job_dir(runtime_context.RUNTIME_PATHS, config, job_id)


def _is_truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


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


def _parse_page_count(raw_value: Any, config: dict[str, Any]) -> int:
    value = config.get("default_pages") if raw_value is None or str(raw_value).strip() == "" else raw_value
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError("页数必须是整数。") from None


def api_job_status(job_id: str):
    config = read_config()
    job_dir = _resolve_job_dir(config, job_id)
    state, _record = get_job_state_snapshot(job_id, job_dir)
    if not state:
        return api_error("任务不存在", 404)
    return jsonify(state)


def api_job_stream(job_id: str):
    config = read_config()
    job_dir = _resolve_job_dir(config, job_id)
    initial_state, _record = get_job_state_snapshot(job_id, job_dir)
    if not initial_state:
        return api_error("任务不存在", 404)

    @stream_with_context
    def event_stream():
        last_payload = ""
        heartbeat_at = time.monotonic()
        last_version = JOB_EVENT_BUS.job_version(job_id)
        yield "retry: 1500\n\n"
        while True:
            state, _record = get_job_state_snapshot(job_id, job_dir)
            if not state:
                yield 'event: error\ndata: {"error":"任务不存在"}\n\n'
                break

            payload = json.dumps(state, ensure_ascii=False)
            if payload != last_payload:
                last_payload = payload
                yield f"event: job\ndata: {payload}\n\n"
                heartbeat_at = time.monotonic()

            resume_control = state.get("resume_control", {}) if isinstance(state.get("resume_control"), dict) else {}
            if state.get("status") in {"completed", "error", "interrupted"} and not resume_control.get("is_waiting_for_stop"):
                break

            now = time.monotonic()
            if now - heartbeat_at >= 15:
                yield ": keep-alive\n\n"
                heartbeat_at = now
            wait_seconds = max(0.1, min(15.0, 15.0 - (time.monotonic() - heartbeat_at)))
            last_version = JOB_EVENT_BUS.wait_for_job_change(job_id, last_version, wait_seconds)

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def api_job_history():
    return jsonify({"items": list_job_summaries(limit=100)})


def api_delete_job(job_id: str):
    record = get_job_record(runtime_context.JOBS_DB_PATH, job_id)
    record = reconcile_job_record(record)
    if not record:
        return api_error("任务不存在", 404)
    if record["status"] in {"queued", "running", "stopping"}:
        return api_error("运行中任务不能删除，请先暂停任务后再删除。")
    remove_job_artifacts(Path(record["job_dir"]))
    delete_job_record(runtime_context.JOBS_DB_PATH, job_id)
    with runtime_context.JOB_STATUS_LOCK:
        runtime_context.JOB_STATUS_CACHE.pop(job_id, None)
    JOB_EVENT_BUS.notify_job_changed(job_id)
    return api_ok()


def api_update_job(job_id: str):
    record = get_job_record(runtime_context.JOBS_DB_PATH, job_id)
    record = reconcile_job_record(record)
    if not record:
        return api_error("任务不存在", 404)

    payload = request.get_json(silent=True) or {}
    fields: dict[str, Any] = {}
    action = str(payload.get("action", "")).strip().lower()

    if "title" in payload:
        title = str(payload.get("title") or "").strip()
        if not title:
            return api_error("任务名称不能为空。")
        fields["title"] = title

    touch_updated_at = True
    if action == "pin":
        fields["pinned_at"] = current_job_timestamp()
        touch_updated_at = False
    elif action == "unpin":
        fields["pinned_at"] = ""
        touch_updated_at = False
    elif action and action != "rename":
        return api_error(f"不支持的任务操作：{action}")

    if not fields:
        return api_error("没有可更新的任务字段。")

    update_job_record(runtime_context.JOBS_DB_PATH, job_id, touch_updated_at=touch_updated_at, **fields)
    refreshed = get_job_record(runtime_context.JOBS_DB_PATH, job_id)
    if not refreshed:
        return api_error("任务不存在", 404)
    return jsonify(job_summary(refreshed))


def api_job_history_stream():
    @stream_with_context
    def event_stream():
        last_payload = ""
        heartbeat_at = time.monotonic()
        last_version = JOB_EVENT_BUS.history_version()
        yield "retry: 2000\n\n"
        while True:
            payload = json.dumps({"items": list_job_summaries(limit=100)}, ensure_ascii=False)
            if payload != last_payload:
                last_payload = payload
                yield f"event: history\ndata: {payload}\n\n"
                heartbeat_at = time.monotonic()
            now = time.monotonic()
            if now - heartbeat_at >= 15:
                yield ": keep-alive\n\n"
                heartbeat_at = now
            wait_seconds = max(0.1, min(15.0, 15.0 - (time.monotonic() - heartbeat_at)))
            last_version = JOB_EVENT_BUS.wait_for_history_change(last_version, wait_seconds)

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def api_interrupt_job(job_id: str):
    record = get_job_record(runtime_context.JOBS_DB_PATH, job_id)
    record = reconcile_job_record(record)
    if not record:
        return api_error("任务不存在", 404)
    if record["status"] not in {"queued", "running"}:
        return api_error("只有运行中任务可以中断。")
    current_stage = str(record.get("current_stage") or "queued")
    job_dir = Path(record["job_dir"])
    request_job_stop(job_dir, job_id)
    updated_state = finalize_job_interrupted(job_dir, job_id, current_stage, INTERRUPTED_MESSAGE)
    update_job_record(
        runtime_context.JOBS_DB_PATH,
        job_id,
        stop_requested=False,
        status="interrupted",
        current_stage=current_stage,
        state=updated_state,
    )
    refreshed_record = get_job_record(runtime_context.JOBS_DB_PATH, job_id) or record
    response_state = enrich_job_state_with_record(updated_state, refreshed_record)
    response_state = attach_delivery_actions(response_state, job_dir)
    attach_resume_control(response_state, refreshed_record, job_dir)
    return jsonify(response_state)


def api_resume_job(job_id: str):
    record = get_job_record(runtime_context.JOBS_DB_PATH, job_id)
    record = reconcile_job_record(record)
    if not record:
        return api_error("任务不存在", 404)
    current_state = record.get("state", {})
    can_resume = record["status"] in {"interrupted", "error"} or can_upgrade_to_editable(current_state)
    if not can_resume:
        return api_error("当前任务状态不支持继续。")
    request_payload = record.get("request", {})
    next_job_target = JOB_TARGET_EDITABLE_PPT
    request_payload["job_target"] = next_job_target
    job_dir = Path(record["job_dir"])
    if is_job_managed(job_id) and has_job_stop_request(job_dir, job_id):
        return api_error("任务后台正在停止，请稍后再继续。")
    update_job_record(
        runtime_context.JOBS_DB_PATH,
        job_id,
        stop_requested=False,
        status="queued",
        request=request_payload,
    )
    clear_job_stop_request(job_dir, job_id)

    mutate_job_state(
        job_dir,
        job_id,
        lambda state: prepare_state_for_resume(state, next_job_target),
    )
    reconcile_resume_state(job_dir, job_id)
    try:
        submit_existing_job_pipeline(record, request_payload=request_payload)
    except ValueError as exc:
        return api_error(exc)
    state = load_job_state(job_id, job_dir)
    if state:
        refreshed_record = get_job_record(runtime_context.JOBS_DB_PATH, job_id) or record
        response_state = attach_delivery_actions(
            enrich_job_state_with_record(state, refreshed_record),
            job_dir,
        )
        attach_resume_control(response_state, refreshed_record, job_dir)
        return jsonify(response_state)
    return api_ok()


def api_get_job_plan(job_id: str):
    record = _get_existing_job_record(job_id)
    if not record:
        return api_error("任务不存在", 404)
    job_dir = Path(record["job_dir"])
    state = _load_editable_job_state(record, job_dir)
    if not state:
        return api_error("任务状态不存在", 404)
    ensure_workflow_metadata(state, record.get("request", {}))
    return jsonify(build_plan_response(state))


def api_update_job_plan(job_id: str):
    record = _get_existing_job_record(job_id)
    if not record:
        return api_error("任务不存在", 404)
    if str(record.get("status") or "").strip() in {"queued", "running", "stopping"}:
        return api_error("任务正在执行中，请先暂停或等待当前阶段完成。")

    payload = request.get_json(silent=True) or {}
    raw_plan = payload.get("plan", payload)
    if not isinstance(raw_plan, dict):
        return api_error("规划内容必须是对象。")

    job_dir = Path(record["job_dir"])

    def updater(state: dict[str, Any]) -> None:
        ensure_workflow_metadata(state, record.get("request", {}))
        normalized_plan = apply_plan_to_state(state, raw_plan)
        save_plan_version(
            state,
            source="user_draft",
            summary=str(payload.get("summary") or "用户保存规划草案"),
            plan=normalized_plan,
        )
        mark_plan_draft(state)
        state["status"] = AWAITING_PLAN_CONFIRMATION_STATUS
        state["current_stage"] = "planning"
        state["error"] = ""
        state["stop_requested"] = False
        _set_stage_status(
            state,
            "planning",
            status="completed",
            summary="规划草案已保存，等待确认后继续生成",
        )

    updated_state = mutate_job_state(job_dir, job_id, updater)
    return jsonify(build_plan_response(updated_state))


def api_confirm_job_plan(job_id: str):
    record = _get_existing_job_record(job_id)
    if not record:
        return api_error("任务不存在", 404)
    if str(record.get("status") or "").strip() in {"queued", "running", "stopping"}:
        return api_error("任务正在执行中，不能重复确认规划。")

    payload = request.get_json(silent=True) or {}
    raw_plan = payload.get("plan")
    if raw_plan is not None and not isinstance(raw_plan, dict):
        return api_error("规划内容必须是对象。")

    job_dir = Path(record["job_dir"])
    request_payload = dict(record.get("request", {}) if isinstance(record.get("request"), dict) else {})

    def updater(state: dict[str, Any]) -> None:
        ensure_workflow_metadata(state, request_payload)
        if isinstance(raw_plan, dict):
            normalized_plan = apply_plan_to_state(state, raw_plan)
        else:
            normalized_plan = get_active_plan_payload(state)
        if not has_complete_planning_state(state):
            raise ValueError("当前规划缺少页面标题或原稿图提示词，暂时不能继续生成。")
        save_plan_version(
            state,
            source="user_confirmed",
            summary=str(payload.get("summary") or "用户确认规划"),
            plan=normalized_plan,
        )
        mark_plan_confirmed(state)
        state["status"] = "queued"
        state["current_stage"] = "planning"
        state["error"] = ""
        state["stop_requested"] = False
        _set_stage_status(
            state,
            "planning",
            status="completed",
            summary=f"规划已确认，共 {len(state.get('pages', []))} 页",
        )

    try:
        updated_state = mutate_job_state(job_dir, job_id, updater)
    except ValueError as exc:
        return api_error(exc)

    request_payload["workflow_mode"] = normalize_workflow_mode(
        request_payload.get("workflow_mode") or updated_state.get("job_meta", {}).get("workflow_mode")
    )
    update_job_record(
        runtime_context.JOBS_DB_PATH,
        job_id,
        stop_requested=False,
        status="queued",
        current_stage="planning",
        request=request_payload,
    )
    clear_job_stop_request(job_dir, job_id)

    refreshed_record = get_job_record(runtime_context.JOBS_DB_PATH, job_id) or record
    try:
        submit_existing_job_pipeline(refreshed_record, request_payload=request_payload)
    except ValueError as exc:
        return api_error(exc)

    state = load_job_state(job_id, job_dir) or updated_state
    return jsonify(state)


def api_deliver_job(job_id: str):
    record = get_job_record(runtime_context.JOBS_DB_PATH, job_id)
    record = reconcile_job_record(record)
    if not record:
        return api_error("任务不存在", 404)
    job_dir = Path(record["job_dir"])
    state, _ = get_job_state_snapshot(job_id, job_dir)
    if not state:
        return api_error("任务状态不存在", 404)
    if record["status"] in {"queued", "running", "stopping"}:
        return api_error("任务仍在运行，请等待当前生成阶段完成后再导出。")

    payload = request.get_json(silent=True) or {}
    delivery_key = str(payload.get("delivery_key", "")).strip()
    if not delivery_key:
        return api_error("缺少 delivery_key。")
    requested_layer_mode = resolve_delivery_action_layer_mode(delivery_key, payload)
    if requested_layer_mode:
        delivery_key = EDITABLE_PPT_DELIVERY_KEY

    job_snapshot = load_job_snapshot(job_dir)
    job_payload = build_job_payload_from_state(state, job_snapshot)
    result_payload = normalize_job_result_payload(job_payload.get("result", {}))

    try:
        if delivery_key == REFERENCE_PPT_DELIVERY_KEY:
            reference_pages = extract_reference_pages_from_state(state)
            if not reference_pages:
                return api_error("原稿图尚未生成完成，暂时不能导出图片PPT。")
            image_preset = state.get("job_meta", {}).get("image_preset", {})
            image_width = int(image_preset.get("width") or read_config().get("image_width", 2048))
            image_height = int(image_preset.get("height") or read_config().get("image_height", 1152))
            output_pptx = job_dir / REFERENCE_PPT_FILENAME
            preview_export = export_reference_images_to_pptx(
                reference_pages,
                job_dir,
                output_pptx,
                image_width=image_width,
                image_height=image_height,
            )
            reference_delivery = build_reference_delivery_payload(
                job_id,
                job_dir,
                output_pptx,
                page_count=int(preview_export["page_count"]),
                logical_page_count=len(reference_pages),
            )
            result_payload = set_reference_delivery(result_payload, reference_delivery)
        elif delivery_key == EDITABLE_PPT_DELIVERY_KEY:
            requested_layer_mode = normalize_editable_delivery_layer_mode(
                requested_layer_mode or payload.get("layer_mode")
            )
            editable_bundle = get_editable_delivery_bundle(result_payload)
            bundle_path = Path(str(editable_bundle.get("bundle_path", "")).strip())
            if not bundle_path.exists():
                return api_error("可编辑元素尚未生成完成，暂时不能导出可编辑PPT。")
            output_pptx = job_dir / build_editable_ppt_filename(requested_layer_mode)
            export_payload = load_cached_editable_delivery(
                bundle_path,
                output_pptx,
                layer_mode=requested_layer_mode,
            )
            if export_payload is None:
                export_payload = export_editable_delivery(
                    bundle_path,
                    output_pptx,
                    layer_mode=requested_layer_mode,
                )
                save_editable_delivery_cache(
                    bundle_path,
                    output_pptx,
                    layer_mode=requested_layer_mode,
                    export_payload=export_payload,
                )
            editable_delivery = build_editable_delivery_payload(job_id, job_dir, export_payload)
            result_payload = set_editable_delivery(
                result_payload,
                editable_delivery,
                layer_mode=requested_layer_mode,
            )
        else:
            return api_error(f"不支持的导出类型：{delivery_key}")
    except Exception as exc:
        return api_error(exc, 500)

    job_payload["result"] = result_payload
    write_job_snapshot(job_dir, job_payload)

    def updater(current_state: dict[str, Any]) -> None:
        current_state["result"] = result_payload

    mutate_job_state(job_dir, job_id, updater)
    refreshed_state, _ = get_job_state_snapshot(job_id, job_dir)
    return jsonify(refreshed_state) if refreshed_state else api_ok()



def serve_run_file(job_id: str, filename: str):
    record = get_job_record(runtime_context.JOBS_DB_PATH, job_id)
    directory = Path(record["job_dir"]) if record and record.get("job_dir") else _resolve_job_dir(read_config(), job_id)
    return send_from_directory(directory, filename)


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
