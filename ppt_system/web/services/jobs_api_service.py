from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from flask import Response, jsonify, request, send_from_directory, stream_with_context

from ppt_system.web.runtime import get_runtime_module
from ppt_system.web.services.job_submission_runtime import (
    bind_submitted_job,
    build_active_config,
    submit_existing_job_pipeline,
)


def _resolve_job_dir(config: dict[str, Any], job_id: str) -> Path:
    runtime = get_runtime_module()
    return runtime.ROOT / str(config["output_dir"]) / job_id


def api_create_job():
    runtime = get_runtime_module()
    config = runtime.read_config()
    content = request.form.get("content", "").strip()
    page_count = int(request.form.get("page_count", config["default_pages"]))
    image_preset_name = request.form.get("image_preset", str(config.get("default_image_preset", "2k")))
    image_quality = request.form.get("image_quality", str(config.get("image_quality", "medium"))).strip().lower()
    job_target = runtime.normalize_job_target(
        request.form.get("job_target", runtime.JOB_TARGET_EDITABLE_PPT),
        runtime.JOB_TARGET_EDITABLE_PPT,
    )
    style_notes = request.form.get("style_notes", "").strip()
    reuse_style_refs_from_job_id = request.form.get("reuse_style_refs_from_job_id", "").strip()
    generation_payload = dict(request.form)
    raw_page_richness_map = request.form.get("page_richness_map", "").strip()
    if raw_page_richness_map:
        try:
            generation_payload["page_richness_map"] = json.loads(raw_page_richness_map)
        except json.JSONDecodeError:
            return jsonify({"error": "逐页内容丰富度参数格式错误。"}), 400
    generation_options = runtime.resolve_generation_options(generation_payload, config=config)

    if not content:
        return jsonify({"error": "请输入内容。"}), 400
    if page_count < 1 or page_count > int(config["max_pages"]):
        return jsonify({"error": f"页数必须在 1 到 {config['max_pages']} 之间。"}), 400

    try:
        image_preset = runtime.resolve_image_preset(config, image_preset_name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    image_width = int(image_preset["width"])
    image_height = int(image_preset["height"])
    if image_quality not in {"low", "medium", "high", "auto"}:
        return jsonify({"error": "图像质量只能选择 low、medium、high 或 auto。"}), 400
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
        source_record = runtime.get_job_record(runtime.JOBS_DB_PATH, reuse_style_refs_from_job_id)
        if source_record:
            runtime.copy_style_reference_images(Path(source_record["job_dir"]), refs_dir)
    style_reference_images = runtime.list_style_reference_images(job_id, job_dir)
    state = runtime.build_job_state(
        job_id,
        content,
        page_count,
        image_preset,
        image_quality,
        style_notes,
        generation_options,
        style_reference_images,
        job_target,
    )
    request_payload = {
        "content": content,
        "page_count": page_count,
        "image_preset": image_preset_name,
        "image_quality": image_quality,
        "style_notes": style_notes,
        "job_target": job_target,
        "generation_options": generation_options,
        "include_cover_page": generation_options["include_cover_page"],
        "page_richness_default": generation_options["page_richness_default"],
        "page_richness_map": generation_options["page_richness_map"],
        "reference_style_adherence": generation_options["reference_style_adherence"],
        "style_reference_images": style_reference_images,
    }
    runtime.create_job_record(
        runtime.JOBS_DB_PATH,
        {
            "job_id": job_id,
            "status": state["status"],
            "current_stage": state["current_stage"],
            "title": runtime.build_job_title(content),
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
    runtime.save_job_state(job_dir, state)
    runtime.mark_job_managed(job_id)
    future = runtime.JOB_EXECUTOR.submit(
        runtime.run_job_pipeline,
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


def api_job_status(job_id: str):
    runtime = get_runtime_module()
    config = runtime.read_config()
    job_dir = _resolve_job_dir(config, job_id)
    state, _record = runtime.get_job_state_snapshot(job_id, job_dir)
    if not state:
        return jsonify({"error": "任务不存在"}), 404
    return jsonify(state)


def api_job_stream(job_id: str):
    runtime = get_runtime_module()
    config = runtime.read_config()
    job_dir = _resolve_job_dir(config, job_id)
    initial_state, _record = runtime.get_job_state_snapshot(job_id, job_dir)
    if not initial_state:
        return jsonify({"error": "任务不存在"}), 404

    @stream_with_context
    def event_stream():
        last_payload = ""
        heartbeat_at = time.monotonic()
        yield "retry: 1500\n\n"
        while True:
            state, _record = runtime.get_job_state_snapshot(job_id, job_dir)
            if not state:
                yield 'event: error\ndata: {"error":"任务不存在"}\n\n'
                break

            payload = json.dumps(state, ensure_ascii=False)
            if payload != last_payload:
                last_payload = payload
                yield f"event: job\ndata: {payload}\n\n"
                heartbeat_at = time.monotonic()

            if state.get("status") in {"completed", "error", "interrupted"}:
                break

            now = time.monotonic()
            if now - heartbeat_at >= 15:
                yield ": keep-alive\n\n"
                heartbeat_at = now
            time.sleep(0.8)

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
    runtime = get_runtime_module()
    return jsonify({"items": runtime.list_job_summaries(limit=100)})


def api_delete_job(job_id: str):
    runtime = get_runtime_module()
    record = runtime.get_job_record(runtime.JOBS_DB_PATH, job_id)
    if not record:
        return jsonify({"error": "任务不存在"}), 404
    if record["status"] in {"queued", "running", "stopping"}:
        return jsonify({"error": "运行中任务不能删除，请先暂停任务后再删除。"}), 400
    runtime.remove_job_artifacts(Path(record["job_dir"]))
    runtime.delete_job_record(runtime.JOBS_DB_PATH, job_id)
    with runtime.JOB_STATUS_LOCK:
        runtime.JOB_STATUS_CACHE.pop(job_id, None)
    return jsonify({"ok": True})


def api_update_job(job_id: str):
    runtime = get_runtime_module()
    record = runtime.get_job_record(runtime.JOBS_DB_PATH, job_id)
    if not record:
        return jsonify({"error": "任务不存在"}), 404

    payload = request.get_json(silent=True) or {}
    fields: dict[str, Any] = {}
    action = str(payload.get("action", "")).strip().lower()

    if "title" in payload:
        title = str(payload.get("title") or "").strip()
        if not title:
            return jsonify({"error": "任务名称不能为空。"}), 400
        fields["title"] = title

    touch_updated_at = True
    if action == "pin":
        fields["pinned_at"] = runtime.current_job_timestamp()
        touch_updated_at = False
    elif action == "unpin":
        fields["pinned_at"] = ""
        touch_updated_at = False
    elif action and action != "rename":
        return jsonify({"error": f"不支持的任务操作：{action}"}), 400

    if not fields:
        return jsonify({"error": "没有可更新的任务字段。"}), 400

    runtime.update_job_record(runtime.JOBS_DB_PATH, job_id, touch_updated_at=touch_updated_at, **fields)
    refreshed = runtime.get_job_record(runtime.JOBS_DB_PATH, job_id)
    if not refreshed:
        return jsonify({"error": "任务不存在"}), 404
    return jsonify(runtime.job_summary(refreshed))


def api_job_history_stream():
    runtime = get_runtime_module()

    @stream_with_context
    def event_stream():
        last_payload = ""
        heartbeat_at = time.monotonic()
        yield "retry: 2000\n\n"
        while True:
            payload = json.dumps({"items": runtime.list_job_summaries(limit=100)}, ensure_ascii=False)
            if payload != last_payload:
                last_payload = payload
                yield f"event: history\ndata: {payload}\n\n"
                heartbeat_at = time.monotonic()
            now = time.monotonic()
            if now - heartbeat_at >= 15:
                yield ": keep-alive\n\n"
                heartbeat_at = now
            time.sleep(1.2)

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
    runtime = get_runtime_module()
    record = runtime.get_job_record(runtime.JOBS_DB_PATH, job_id)
    if not record:
        return jsonify({"error": "任务不存在"}), 404
    if record["status"] not in {"queued", "running"}:
        return jsonify({"error": "只有运行中任务可以中断。"}), 400
    current_stage = str(record.get("current_stage") or "queued")
    runtime.update_job_record(
        runtime.JOBS_DB_PATH,
        job_id,
        stop_requested=True,
        status="stopping",
        current_stage=current_stage,
    )
    job_dir = Path(record["job_dir"])

    def updater(state: dict[str, Any]) -> None:
        state["stop_requested"] = True
        state["status"] = "stopping"
        state["current_stage"] = str(state.get("current_stage") or current_stage)
        for stage in state.get("stages", []):
            if stage.get("key") == state["current_stage"]:
                stage["status"] = "stopping"
                stage["summary"] = runtime.STOPPING_MESSAGE
                logs = stage.setdefault("logs", [])
                if runtime.STOPPING_MESSAGE not in logs:
                    logs.append(runtime.STOPPING_MESSAGE)
                break

    updated_state = runtime.mutate_job_state(job_dir, job_id, updater)
    refreshed_record = runtime.get_job_record(runtime.JOBS_DB_PATH, job_id) or record
    response_state = runtime.enrich_job_state_with_record(updated_state, refreshed_record)
    return jsonify(runtime.attach_delivery_actions(response_state, job_dir))


def api_resume_job(job_id: str):
    runtime = get_runtime_module()
    record = runtime.get_job_record(runtime.JOBS_DB_PATH, job_id)
    if not record:
        return jsonify({"error": "任务不存在"}), 404
    current_state = record.get("state", {})
    can_resume = record["status"] in {"interrupted", "error"} or runtime.can_upgrade_to_editable(current_state)
    if not can_resume:
        return jsonify({"error": "当前任务状态不支持继续。"}), 400
    request_payload = record.get("request", {})
    next_job_target = runtime.JOB_TARGET_EDITABLE_PPT
    request_payload["job_target"] = next_job_target
    job_dir = Path(record["job_dir"])
    runtime.update_job_record(
        runtime.JOBS_DB_PATH,
        job_id,
        stop_requested=False,
        status="queued",
        request=request_payload,
    )

    def updater(state: dict[str, Any]) -> None:
        state["stop_requested"] = False
        state["status"] = "queued"
        state["error"] = ""
        state.setdefault("job_meta", {})["job_target"] = next_job_target
        state["job_meta"]["job_target_label"] = runtime.TARGET_LABELS[next_job_target]
        for stage in state.get("stages", []):
            if stage.get("key") in {"elements_generation", "ppt_export"} and stage.get("status") == "skipped":
                stage["status"] = "pending"
                stage["summary"] = "等待继续执行"

    runtime.mutate_job_state(job_dir, job_id, updater)
    runtime.reconcile_resume_state(job_dir, job_id)
    try:
        submit_existing_job_pipeline(record, request_payload=request_payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    state = runtime.load_job_state(job_id, job_dir)
    return jsonify(state or {"ok": True})


def api_deliver_job(job_id: str):
    runtime = get_runtime_module()
    record = runtime.get_job_record(runtime.JOBS_DB_PATH, job_id)
    if not record:
        return jsonify({"error": "任务不存在"}), 404
    job_dir = Path(record["job_dir"])
    state, _ = runtime.get_job_state_snapshot(job_id, job_dir)
    if not state:
        return jsonify({"error": "任务状态不存在"}), 404
    if record["status"] in {"queued", "running", "stopping"}:
        return jsonify({"error": "任务仍在运行，请等待当前生成阶段完成后再导出。"}), 400

    payload = request.get_json(silent=True) or {}
    delivery_key = str(payload.get("delivery_key", "")).strip()
    if not delivery_key:
        return jsonify({"error": "缺少 delivery_key。"}), 400
    requested_layer_mode = _resolve_delivery_action_layer_mode(runtime, delivery_key, payload)
    if requested_layer_mode:
        delivery_key = runtime.EDITABLE_PPT_DELIVERY_KEY

    job_snapshot = runtime.load_job_snapshot(job_dir)
    job_payload = runtime.build_job_payload_from_state(state, job_snapshot)
    result_payload = runtime.normalize_job_result_payload(job_payload.get("result", {}))

    try:
        if delivery_key == runtime.REFERENCE_PPT_DELIVERY_KEY:
            reference_pages = runtime.extract_reference_pages_from_state(state)
            if not reference_pages:
                return jsonify({"error": "原稿图尚未生成完成，暂时不能导出图片PPT。"}), 400
            image_preset = state.get("job_meta", {}).get("image_preset", {})
            image_width = int(image_preset.get("width") or runtime.read_config().get("image_width", 2048))
            image_height = int(image_preset.get("height") or runtime.read_config().get("image_height", 1152))
            output_pptx = job_dir / runtime.REFERENCE_PPT_FILENAME
            preview_export = runtime.export_reference_images_to_pptx(
                reference_pages,
                job_dir,
                output_pptx,
                image_width=image_width,
                image_height=image_height,
            )
            reference_delivery = runtime.build_reference_delivery_payload(
                job_id,
                job_dir,
                output_pptx,
                page_count=int(preview_export["page_count"]),
                logical_page_count=len(reference_pages),
            )
            result_payload = runtime.set_reference_delivery(result_payload, reference_delivery)
        elif delivery_key == runtime.EDITABLE_PPT_DELIVERY_KEY:
            requested_layer_mode = runtime.normalize_editable_delivery_layer_mode(
                requested_layer_mode or payload.get("layer_mode")
            )
            editable_bundle = runtime.get_editable_delivery_bundle(result_payload)
            bundle_path = Path(str(editable_bundle.get("bundle_path", "")).strip())
            if not bundle_path.exists():
                return jsonify({"error": "可编辑元素尚未生成完成，暂时不能导出可编辑PPT。"}), 400
            output_pptx = job_dir / runtime.build_editable_ppt_filename(requested_layer_mode)
            export_payload = runtime.export_editable_delivery(
                bundle_path,
                output_pptx,
                layer_mode=requested_layer_mode,
            )
            editable_delivery = runtime.build_editable_delivery_payload(job_id, job_dir, export_payload)
            result_payload = runtime.set_editable_delivery(
                result_payload,
                editable_delivery,
                layer_mode=requested_layer_mode,
            )
        else:
            return jsonify({"error": f"不支持的导出类型：{delivery_key}"}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    job_payload["result"] = result_payload
    runtime.write_job_snapshot(job_dir, job_payload)

    def updater(current_state: dict[str, Any]) -> None:
        current_state["result"] = result_payload

    runtime.mutate_job_state(job_dir, job_id, updater)
    refreshed_state, _ = runtime.get_job_state_snapshot(job_id, job_dir)
    return jsonify(refreshed_state or {"ok": True})


def _resolve_delivery_action_layer_mode(runtime: Any, delivery_key: str, payload: dict[str, Any]) -> str:
    if delivery_key == runtime.EDITABLE_SINGLE_PAGE_DELIVERY_ACTION_KEY:
        return runtime.OVERLAY_LAYER_MODE
    if delivery_key == runtime.EDITABLE_SPLIT_PAGES_DELIVERY_ACTION_KEY:
        return runtime.SEPARATE_LAYER_MODE
    if delivery_key == runtime.EDITABLE_PPT_DELIVERY_KEY:
        return str(payload.get("layer_mode", "")).strip()
    return ""


def serve_run_file(job_id: str, filename: str):
    runtime = get_runtime_module()
    config = runtime.read_config()
    directory = _resolve_job_dir(config, job_id)
    return send_from_directory(directory, filename)
