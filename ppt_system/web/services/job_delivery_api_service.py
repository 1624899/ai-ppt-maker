from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import jsonify, request

from ppt_system.export.delivery_options import (
    EDITABLE_PPT_DELIVERY_KEY,
    REFERENCE_PPT_DELIVERY_KEY,
    REFERENCE_PPT_FILENAME,
    build_editable_ppt_filename,
    normalize_editable_delivery_layer_mode,
)
from ppt_system.export.editable_delivery_cache import load_cached_editable_delivery, save_editable_delivery_cache
from ppt_system.export.export_pipeline import export_editable_delivery
from ppt_system.export.reference_preview_export import export_reference_images_to_pptx
from ppt_system.jobs.job_delivery_state import (
    build_editable_delivery_payload,
    build_reference_delivery_payload,
    get_editable_delivery_bundle,
    normalize_job_result_payload,
    set_editable_delivery,
    set_reference_delivery,
)
from ppt_system.jobs.job_store import get_job as get_job_record
from ppt_system.runtime import runtime_context
from ppt_system.web.services.api_response import api_error, api_ok
from ppt_system.web.services.app_config_runtime import read_config
from ppt_system.web.services.job_snapshot_runtime import (
    build_job_payload_from_state,
    load_job_snapshot,
    resolve_delivery_action_layer_mode,
    write_job_snapshot,
)
from ppt_system.web.services.job_state_model import extract_reference_pages_from_state
from ppt_system.web.services.job_state_reconciliation import reconcile_job_record
from ppt_system.web.services.job_state_store import mutate_job_state
from ppt_system.web.services.job_state_view import get_job_state_snapshot

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
