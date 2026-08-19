from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ppt_system.export.stage_labels import normalize_stage_label
from ppt_system.generation.generation_options import resolve_generation_options
from ppt_system.jobs.active_job_registry import is_job_managed
from ppt_system.jobs.job_delivery_state import attach_delivery_actions
from ppt_system.jobs.job_interrupt_signal import has_job_stop_request
from ppt_system.jobs.job_store import get_job as get_job_record
from ppt_system.jobs.job_store import list_jobs as list_job_records
from ppt_system.jobs.job_targets import (
    JOB_TARGET_EDITABLE_PPT,
    TARGET_LABELS,
    can_upgrade_to_editable,
    normalize_job_target,
)
from ppt_system.runtime import runtime_context
from ppt_system.runtime.app_paths import resolve_configured_output_root
from ppt_system.web.services.app_config_runtime import list_style_reference_images, read_config, resolve_image_preset
from ppt_system.web.services.job_state_model import (
    merge_record_runtime_fields,
    normalize_job_state_labels,
    reconcile_job_runtime_status,
)
from ppt_system.web.services.job_state_reconciliation import reconcile_job_record
from ppt_system.web.services.job_state_store import load_job_state
from ppt_system.web.services.job_edit_history import build_job_edit_summary
from ppt_system.web.services.workflow_policy import (
    ensure_workflow_metadata,
    get_workflow_mode_label,
    normalize_workflow_mode,
)

def get_job_state_snapshot(job_id: str, job_dir: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    record = get_job_record(runtime_context.JOBS_DB_PATH, job_id)
    record = reconcile_job_record(record)
    if record:
        state = record.get("state", {})
        if isinstance(state, dict) and state:
            enriched = normalize_job_state_labels(enrich_job_state_with_record(state, record))
            response_state = attach_delivery_actions(enriched, job_dir)
            attach_resume_control(response_state, record, job_dir)
            return response_state, record
    state = load_job_state(job_id, job_dir)
    if not state:
        return None, record
    enriched = normalize_job_state_labels(enrich_job_state_with_record(state, record))
    response_state = attach_delivery_actions(enriched, job_dir)
    attach_resume_control(response_state, record, job_dir)
    return response_state, record

def attach_resume_control(state: dict[str, Any], record: dict[str, Any] | None, job_dir: Path) -> None:
    job_id = str((record or {}).get("job_id") or state.get("job_id") or "").strip()
    resolved_job_dir = Path(str((record or {}).get("job_dir") or job_dir))
    record_status = str((record or {}).get("status") or "").strip()
    status = record_status or str(state.get("status") or "").strip()
    stop_requested = bool((record or {}).get("stop_requested") or state.get("stop_requested"))
    is_managed = bool(job_id and is_job_managed(job_id))
    has_stop_signal = bool(job_id and has_job_stop_request(resolved_job_dir, job_id))
    is_waiting_for_stop = status == "stopping" or (is_managed and (has_stop_signal or stop_requested))
    status_can_resume = status in {"interrupted", "error"} or can_upgrade_to_editable(state)

    state["resume_control"] = {
        "can_resume": bool(status_can_resume and not is_waiting_for_stop),
        "is_waiting_for_stop": bool(is_waiting_for_stop),
        "label": "停止收尾中" if is_waiting_for_stop else "继续生成",
        "message": "正在等待当前图片请求或导出步骤收尾，完成后会自动恢复继续按钮。" if is_waiting_for_stop else "",
    }

def _find_preview_image(state: dict[str, Any]) -> str:
    for collection_name in ("element_pages", "reference_pages", "pages"):
        collection = state.get(collection_name, [])
        if not isinstance(collection, list):
            continue
        for page in collection:
            if not isinstance(page, dict):
                continue
            for key in ("element_image", "reference_image", "image"):
                image = str(page.get(key, "")).strip()
                if image:
                    return image
    return ""

def _normalize_style_reference_images(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "")).strip()
        if not url:
            continue
        normalized.append(
            {
                "name": str(item.get("name", "")).strip(),
                "url": url,
                "size": _normalize_file_size(item.get("size")),
            }
        )
    return normalized

def _normalize_file_size(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0

def _find_style_reference_images(record: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
    job_meta = state.get("job_meta", {})
    if isinstance(job_meta, dict):
        from_state = _normalize_style_reference_images(job_meta.get("style_reference_images"))
        if from_state:
            return from_state

    request_payload = record.get("request", {})
    if isinstance(request_payload, dict):
        from_request = _normalize_style_reference_images(request_payload.get("style_reference_images"))
        if from_request:
            return from_request

    job_dir = str(record.get("job_dir") or "").strip()
    job_id = str(record.get("job_id") or "").strip()
    if not job_dir or not job_id:
        return []
    return _normalize_style_reference_images(list_style_reference_images(job_id, Path(job_dir)))

def _summarize_stage_progress(state: dict[str, Any]) -> list[dict[str, Any]]:
    stages = state.get("stages", [])
    if not isinstance(stages, list):
        return []
    summarized: list[dict[str, Any]] = []
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        key = str(stage.get("key") or "").strip()
        summarized.append(
            {
                "key": key,
                "label": normalize_stage_label(key, stage.get("label")),
                "status": str(stage.get("status") or "").strip(),
                "summary": str(stage.get("summary") or "").strip(),
            }
        )
    return summarized

def job_summary(record: dict[str, Any]) -> dict[str, Any]:
    state = record.get("state", {}) if isinstance(record.get("state"), dict) else {}
    job_meta = state.get("job_meta", {}) if isinstance(state.get("job_meta"), dict) else {}
    request_payload = record.get("request", {}) if isinstance(record.get("request"), dict) else {}
    workflow_mode = normalize_workflow_mode(
        job_meta.get("workflow_mode") or request_payload.get("workflow_mode")
    )
    edit_summary = build_job_edit_summary(state, record)
    return {
        "job_id": record["job_id"],
        "title": record["title"],
        "status": record["status"],
        "current_stage": record["current_stage"],
        "page_count": record["page_count"],
        "image_preset": record["image_preset"],
        "image_quality": record["image_quality"],
        "style_notes": edit_summary["style_notes"],
        "has_user_edits": edit_summary["has_user_edits"],
        "edit_count": edit_summary["edit_count"],
        "last_edit_summary": edit_summary["last_edit_summary"],
        "last_edited_at": edit_summary["last_edited_at"],
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "pinned_at": str(record.get("pinned_at") or ""),
        "stop_requested": record.get("stop_requested", False),
        "stages": _summarize_stage_progress(state),
        "preview_image": _find_preview_image(state),
        "style_reference_images": _find_style_reference_images(record, state),
        "workflow_mode": workflow_mode,
        "workflow_mode_label": get_workflow_mode_label(workflow_mode),
    }

def enrich_job_state_with_record(state: dict[str, Any], record: dict[str, Any] | None) -> dict[str, Any]:
    merged = json.loads(json.dumps(state, ensure_ascii=False))
    if not record:
        ensure_workflow_metadata(merged)
        return normalize_job_state_labels(reconcile_job_runtime_status(merged))
    merge_record_runtime_fields(merged, record)
    merged["title"] = str(record.get("title") or merged.get("title") or "")
    merged["pinned_at"] = str(record.get("pinned_at") or "")
    job_meta = merged.setdefault("job_meta", {})
    ensure_workflow_metadata(merged, record.get("request", {}))
    job_meta["content"] = str(job_meta.get("content") or record.get("content") or "")
    job_meta["page_count"] = int(job_meta.get("page_count") or record.get("page_count") or 0)
    job_meta["image_quality"] = str(job_meta.get("image_quality") or record.get("image_quality") or "")
    job_meta["style_notes"] = str(job_meta.get("style_notes") or record.get("style_notes") or "")
    job_target = normalize_job_target(
        job_meta.get("job_target") or record.get("request", {}).get("job_target"),
        JOB_TARGET_EDITABLE_PPT,
    )
    job_meta["job_target"] = job_target
    job_meta["job_target_label"] = TARGET_LABELS.get(job_target, TARGET_LABELS[JOB_TARGET_EDITABLE_PPT])
    if not isinstance(job_meta.get("generation_options"), dict):
        job_meta["generation_options"] = resolve_generation_options(record.get("request", {}), config=read_config())
    if not job_meta.get("image_preset"):
        config = read_config()
        try:
            job_meta["image_preset"] = resolve_image_preset(config, str(record.get("image_preset") or ""))
        except ValueError:
            job_meta["image_preset"] = {
                "name": str(record.get("image_preset") or ""),
                "label": str(record.get("image_preset") or ""),
            }
    if not isinstance(job_meta.get("style_reference_images"), list) or not job_meta.get("style_reference_images"):
        job_meta["style_reference_images"] = list_style_reference_images(str(record["job_id"]), Path(record["job_dir"]))
    return normalize_job_state_labels(reconcile_job_runtime_status(merged))

def list_job_summaries(limit: int = 100) -> list[dict[str, Any]]:
    records = [
        reconcile_job_record(record) or record
        for record in list_job_records(runtime_context.JOBS_DB_PATH, limit=limit)
    ]
    return [job_summary(record) for record in records]

def remove_job_artifacts(job_dir: Path) -> None:
    if not job_dir.exists():
        return
    try:
        resolved = job_dir.resolve()
    except OSError:
        return
    config = read_config()
    output_root = resolve_configured_output_root(runtime_context.RUNTIME_PATHS, config)
    if resolved == output_root or output_root not in resolved.parents:
        return
    shutil.rmtree(resolved, ignore_errors=True)
