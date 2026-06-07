from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from flask import jsonify, request

from ppt_system.integrations.model_config import get_active_model_config
from ppt_system.integrations.openai_image_provider import OpenAIImageProvider
from ppt_system.runtime.time_utils import utc_iso_timestamp
from ppt_system.web.runtime import get_runtime_module
from ppt_system.web.services import job_operations_service
from ppt_system.web.services.api_response import api_error
from ppt_system.web.services.job_artifact_paths import resolve_job_artifact_path
from ppt_system.web.services.job_stage_requeue import activate_requeued_stage, reset_stages_after_artifact_change
from ppt_system.web.services.job_submission_runtime import build_active_config, submit_existing_job_pipeline


RUNNING_STATUSES = {"queued", "running", "stopping"}
MAX_IMAGE_EDIT_CANDIDATES = 60
IMAGE_SLOTS = {
    "reference": {
        "label": "原稿图",
        "page_field": "reference_image",
        "collection": "reference_pages",
        "status_after_apply": "reference_done",
    },
    "element": {
        "label": "元素图",
        "page_field": "element_image",
        "collection": "element_pages",
        "status_after_apply": "completed",
    },
    "preview": {
        "label": "预览图",
        "page_field": "image",
        "collection": "",
        "status_after_apply": "",
    },
}


def api_create_image_edit_candidate(job_id: str):
    payload = request.get_json(silent=True) or {}
    try:
        state = create_image_edit_candidate(job_id, payload)
    except ValueError as exc:
        return api_error(exc)
    except FileNotFoundError as exc:
        return api_error(exc, 404)
    except RuntimeError as exc:
        status = 409 if "正在运行" in str(exc) else 502
        return api_error(exc, status)
    return jsonify(state)


def api_apply_image_edit_candidate(job_id: str, candidate_id: str):
    try:
        state = apply_image_edit_candidate(job_id, candidate_id)
    except ValueError as exc:
        return api_error(exc)
    except FileNotFoundError as exc:
        return api_error(exc, 404)
    except RuntimeError as exc:
        status = 409 if "正在运行" in str(exc) else 500
        return api_error(exc, status)
    return jsonify(state)


def create_image_edit_candidate(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    runtime = get_runtime_module()
    record, state, job_dir = _load_record_and_state(runtime, job_id)
    _ensure_not_running(record)

    page_no = _coerce_page_no(payload.get("page_no"))
    preview_type = _normalize_preview_type(payload.get("preview_type"))
    instruction = _normalize_instruction(payload.get("instruction"))
    if not instruction:
        raise ValueError("请先填写文字描述调整。")

    page = job_operations_service._find_page(state, page_no)
    source_image = _resolve_source_image(page, state, page_no, preview_type)
    source_path = resolve_job_artifact_path(job_dir, job_id, source_image)
    if source_path is None:
        slot_label = IMAGE_SLOTS[preview_type]["label"]
        raise FileNotFoundError(f"第 {page_no} 页还没有可编辑的{slot_label}。")

    annotations = _normalize_annotations(payload.get("annotations"))
    config = runtime.read_config()
    active_config = _build_active_image_config(runtime, config, record, state)
    image_profile = get_active_model_config(config, "image")
    image_provider = OpenAIImageProvider(active_config, image_profile)

    candidate_id = uuid.uuid4().hex[:12]
    output_dir = job_dir / "04_image_edits" / f"page_{page_no:02d}"
    output_path = output_dir / f"{candidate_id}_{preview_type}.png"
    prompt_path = output_dir / f"{candidate_id}_prompt.txt"
    metadata_path = output_dir / f"{candidate_id}_metadata.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt = build_image_edit_prompt(
        page=page,
        instruction=instruction,
        annotations=annotations,
        preview_type=preview_type,
        image_width=int(active_config.get("image_width", 2048)),
        image_height=int(active_config.get("image_height", 1152)),
    )
    prompt_path.write_text(prompt, encoding="utf-8")
    request_meta = _build_image_edit_request_metadata(
        candidate_id=candidate_id,
        job_id=job_id,
        page_no=page_no,
        preview_type=preview_type,
        instruction=instruction,
        annotations=annotations,
        prompt=prompt,
        prompt_path=prompt_path,
        metadata_path=metadata_path,
        source_image=source_image,
        source_path=source_path,
        output_path=output_path,
        active_config=active_config,
        image_profile=image_profile,
        image_provider=image_provider,
    )
    _write_image_edit_metadata(metadata_path, {**request_meta, "status": "submitting"})
    try:
        generation_meta = image_provider.generate_edited_image(prompt, output_path, [source_path])
    except Exception as exc:
        _write_image_edit_metadata(
            metadata_path,
            {
                **request_meta,
                "status": "error",
                "error": str(exc),
                "updated_at": _timestamp(),
            },
        )
        raise
    _write_image_edit_metadata(
        metadata_path,
        {
            **request_meta,
            "status": "generated",
            "generation": generation_meta,
            "updated_at": _timestamp(),
        },
    )

    candidate = {
        "candidate_id": candidate_id,
        "page_no": page_no,
        "preview_type": preview_type,
        "preview_label": IMAGE_SLOTS[preview_type]["label"],
        "instruction": instruction,
        "prompt": prompt,
        "annotations": annotations,
        "source_image": source_image,
        "image": f"/runs/{job_id}/04_image_edits/page_{page_no:02d}/{output_path.name}",
        "prompt_file": f"/runs/{job_id}/04_image_edits/page_{page_no:02d}/{prompt_path.name}",
        "metadata_file": f"/runs/{job_id}/04_image_edits/page_{page_no:02d}/{metadata_path.name}",
        "generation": generation_meta,
        "status": "generated",
        "created_at": _timestamp(),
        "updated_at": _timestamp(),
    }

    def updater(current_state: dict[str, Any]) -> None:
        candidates = current_state.setdefault("image_edit_candidates", [])
        if not isinstance(candidates, list):
            candidates = []
            current_state["image_edit_candidates"] = candidates
        candidates.append(json.loads(json.dumps(candidate, ensure_ascii=False)))
        del candidates[:-MAX_IMAGE_EDIT_CANDIDATES]

    updated_state = runtime.mutate_job_state(job_dir, job_id, updater)
    _sync_job_snapshot(runtime, job_dir, updated_state)
    return runtime.attach_delivery_actions(updated_state, job_dir)


def apply_image_edit_candidate(job_id: str, candidate_id: str) -> dict[str, Any]:
    runtime = get_runtime_module()
    record, state, job_dir = _load_record_and_state(runtime, job_id)
    _ensure_not_running(record)

    candidate = _find_candidate(state, candidate_id)
    if str(candidate.get("status", "")) == "applied":
        return runtime.attach_delivery_actions(state, job_dir)

    page_no = _coerce_page_no(candidate.get("page_no"))
    preview_type = _normalize_preview_type(candidate.get("preview_type"))
    candidate_path = resolve_job_artifact_path(job_dir, job_id, str(candidate.get("image", "")))
    if candidate_path is None:
        raise FileNotFoundError("编辑预览图文件不存在，无法替换。")

    version = job_operations_service._create_page_version(
        job_id,
        job_dir,
        state,
        page_no,
        f"image_edit_{candidate_id}",
        reason="before_image_edit_apply",
    )

    def updater(current_state: dict[str, Any]) -> None:
        job_operations_service._append_page_version(current_state, version)
        current_candidate = _find_candidate(current_state, candidate_id)
        _apply_candidate_to_page(current_state, current_candidate)
        current_candidate["status"] = "applied"
        current_candidate["applied_at"] = _timestamp()
        current_candidate["updated_at"] = _timestamp()
        current_candidate["version_id"] = version["version_id"]
        _append_apply_operation(current_state, current_candidate, version)
        _invalidate_delivery_result(current_state)
        _reset_followup_stages_after_apply(current_state, current_candidate)

    should_submit_pipeline = _apply_requeues_pipeline(preview_type)
    updated_state = runtime.mutate_job_state(job_dir, job_id, updater)
    if _should_submit_pipeline_after_apply(updated_state, preview_type):
        job_operations_service._invalidate_job_snapshot_result(runtime, job_dir)
        activation_summary = _build_requeue_running_summary(preview_type)
        updated_state = _mark_requeued_pipeline_submitting(runtime, job_dir, job_id, activation_summary)
        _sync_job_snapshot(runtime, job_dir, updated_state)
        try:
            submit_existing_job_pipeline(record)
        except Exception as exc:
            updated_state = _mark_requeue_submission_failed(runtime, job_dir, job_id, preview_type, exc)
            _sync_job_snapshot(runtime, job_dir, updated_state)
            raise
    elif should_submit_pipeline:
        job_operations_service._invalidate_job_snapshot_result(runtime, job_dir)
        _sync_job_snapshot(runtime, job_dir, updated_state)
    else:
        _sync_job_snapshot(runtime, job_dir, updated_state)
    response_state = runtime.attach_delivery_actions(updated_state, job_dir)
    refreshed_record = runtime.get_job_record(runtime.JOBS_DB_PATH, job_id) or record
    runtime.attach_resume_control(response_state, refreshed_record, job_dir)
    return response_state


def build_image_edit_prompt(
    *,
    page: dict[str, Any],
    instruction: str,
    annotations: list[dict[str, Any]],
    preview_type: str,
    image_width: int,
    image_height: int,
) -> str:
    slot_label = IMAGE_SLOTS[_normalize_preview_type(preview_type)]["label"]
    title = _normalize_instruction(page.get("title")) or f"第 {page.get('page_no', '')} 页"
    summary = _normalize_instruction(page.get("summary"))
    lines = [
        f"请基于上传的{slot_label}进行图片编辑，输出一张 {image_width}x{image_height}、16:9 的中文 PPT 单页图。",
        "只修改用户明确要求调整的内容，其他版式、比例、视觉语言和可读文字尽量保持稳定。",
        f"页面标题：{title}",
    ]
    if summary:
        lines.append(f"页面摘要：{summary}")
    lines.extend(
        [
            f"本次修改要求：{instruction}",
            "如果修改只涉及文字或局部布局，请避免整页无关重绘；如果涉及被框选区域，请优先处理对应区域。",
            "保持中文文字清晰可读，不要生成乱码，不要把 PPT 页面改成照片或海报。",
        ]
    )
    if annotations:
        lines.append("框选标注采用归一化坐标，x/y/width/height 均为 0 到 1 的相对比例：")
        for index, annotation in enumerate(annotations, start=1):
            box = annotation.get("box", {})
            label = _normalize_instruction(annotation.get("label")) or f"区域 {index}"
            lines.append(
                f"- 区域 {index}「{label}」："
                f"x={_format_ratio(box.get('x'))}, y={_format_ratio(box.get('y'))}, "
                f"width={_format_ratio(box.get('width'))}, height={_format_ratio(box.get('height'))}"
            )
    else:
        lines.append("本次没有框选标注，请根据文字描述判断修改对象。")
    return "\n".join(line for line in lines if str(line).strip())


def _load_record_and_state(runtime: Any, job_id: str) -> tuple[dict[str, Any], dict[str, Any], Path]:
    record = runtime.get_job_record(runtime.JOBS_DB_PATH, job_id)
    if not record:
        raise FileNotFoundError("任务不存在")
    job_dir = Path(record["job_dir"])
    state, _ = runtime.get_job_state_snapshot(job_id, job_dir)
    if not state:
        raise FileNotFoundError("任务状态不存在")
    return record, state, job_dir


def _ensure_not_running(record: dict[str, Any]) -> None:
    if str(record.get("status")) in RUNNING_STATUSES:
        raise RuntimeError("当前任务正在运行，请等待完成或停止后再操作。")


def _build_active_image_config(
    runtime: Any,
    config: dict[str, Any],
    record: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    request_payload = record.get("request", {}) if isinstance(record.get("request"), dict) else {}
    job_meta = state.get("job_meta", {}) if isinstance(state.get("job_meta"), dict) else {}
    image_preset = job_meta.get("image_preset") if isinstance(job_meta.get("image_preset"), dict) else {}
    if not _is_valid_image_preset(image_preset):
        image_preset = runtime.resolve_image_preset(
            config,
            str(request_payload.get("image_preset") or config.get("default_image_preset", "")),
        )
    image_quality = str(
        request_payload.get("image_quality")
        or record.get("image_quality")
        or job_meta.get("image_quality")
        or config.get("image_quality", "medium")
    )
    return build_active_config(config, image_preset, image_quality)


def _is_valid_image_preset(value: Any) -> bool:
    return isinstance(value, dict) and all(value.get(key) for key in ("width", "height", "size"))


def _resolve_source_image(
    page: dict[str, Any],
    state: dict[str, Any],
    page_no: int,
    preview_type: str,
) -> str:
    slot = IMAGE_SLOTS[preview_type]
    image = _normalize_instruction(page.get(slot["page_field"]))
    if image:
        return image
    collection_name = str(slot.get("collection") or "")
    if collection_name:
        artifact = job_operations_service._find_artifact(state.get(collection_name), page_no)
        image = _normalize_instruction(artifact.get("image"))
        if image:
            return image
    return ""


def _find_candidate(state: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    requested = str(candidate_id or "").strip()
    for candidate in state.get("image_edit_candidates", []):
        if isinstance(candidate, dict) and str(candidate.get("candidate_id", "")) == requested:
            return candidate
    raise ValueError(f"找不到编辑预览：{requested or '空'}")


def _apply_candidate_to_page(state: dict[str, Any], candidate: dict[str, Any]) -> None:
    page_no = _coerce_page_no(candidate.get("page_no"))
    preview_type = _normalize_preview_type(candidate.get("preview_type"))
    slot = IMAGE_SLOTS[preview_type]
    page = job_operations_service._find_page(state, page_no)
    page[slot["page_field"]] = candidate["image"]
    if slot["status_after_apply"]:
        page["status"] = slot["status_after_apply"]
    if preview_type == "reference":
        page["reference_prompt"] = candidate.get("prompt", page.get("reference_prompt", ""))
        page["element_image"] = ""
        job_operations_service._remove_artifact(state, "element_pages", page_no)
    elif preview_type == "element":
        page["elements_prompt"] = candidate.get("prompt", page.get("elements_prompt", ""))

    collection_name = str(slot.get("collection") or "")
    if collection_name:
        artifact = {
            "page_no": page_no,
            "title": page.get("title", f"第 {page_no} 页"),
            "prompt": candidate.get("prompt", ""),
            "image": candidate["image"],
            "generation": candidate.get("generation", {}),
            "source_image": candidate.get("source_image", ""),
            "edit_candidate_id": candidate.get("candidate_id", ""),
        }
        job_operations_service._upsert_artifact(state, collection_name, artifact)


def _reset_followup_stages_after_apply(state: dict[str, Any], candidate: dict[str, Any]) -> None:
    preview_type = _normalize_preview_type(candidate.get("preview_type"))
    page_no = _coerce_page_no(candidate.get("page_no"))
    if preview_type == "reference":
        reset_stages_after_artifact_change(
            state,
            changed_stage="reference_generation",
            page_numbers=(page_no,),
            summary="原稿图已替换，等待重新生成元素图与可编辑结果",
        )
    elif preview_type == "element":
        reset_stages_after_artifact_change(
            state,
            changed_stage="elements_generation",
            page_numbers=(page_no,),
            summary="元素图已替换，等待重建可编辑结果",
        )


def _should_submit_pipeline_after_apply(state: dict[str, Any], preview_type: str) -> bool:
    if not _apply_requeues_pipeline(preview_type):
        return False
    return str(state.get("status") or "") == "queued"


def _apply_requeues_pipeline(preview_type: str) -> bool:
    return preview_type in {"reference", "element"}


def _build_requeue_running_summary(preview_type: str) -> str:
    if _normalize_preview_type(preview_type) == "reference":
        return "原稿图已替换，正在重新生成元素图与可编辑结果"
    if _normalize_preview_type(preview_type) == "element":
        return "元素图已替换，正在重建可编辑 PPT"
    return "正在继续处理更新后的图片产物"


def _mark_requeued_pipeline_submitting(
    runtime: Any,
    job_dir: Path,
    job_id: str,
    summary: str,
) -> dict[str, Any]:
    def updater(current_state: dict[str, Any]) -> None:
        if str(current_state.get("status") or "") == "queued":
            activate_requeued_stage(current_state, summary=summary)

    return runtime.mutate_job_state(job_dir, job_id, updater)


def _mark_requeue_submission_failed(
    runtime: Any,
    job_dir: Path,
    job_id: str,
    preview_type: str,
    exc: Exception,
) -> dict[str, Any]:
    message = f"{IMAGE_SLOTS[_normalize_preview_type(preview_type)]['label']}已替换，但自动继续生成提交失败：{exc}"

    def updater(current_state: dict[str, Any]) -> None:
        current_state["status"] = "error"
        current_state["error"] = message
        current_state["stop_requested"] = False
        stage_key = str(current_state.get("current_stage") or "").strip()
        now = utc_iso_timestamp()
        for stage in current_state.get("stages", []):
            if not isinstance(stage, dict) or str(stage.get("key") or "") != stage_key:
                continue
            stage["status"] = "error"
            stage["summary"] = message
            stage["updated_at"] = now
            logs = stage.setdefault("logs", [])
            if isinstance(logs, list):
                logs.append(message)
            break

    updated_state = runtime.mutate_job_state(job_dir, job_id, updater)
    runtime.update_job_record(
        runtime.JOBS_DB_PATH,
        job_id,
        status="error",
        current_stage=updated_state.get("current_stage", ""),
        state=updated_state,
        result=updated_state.get("result", {}),
        stop_requested=False,
    )
    return updated_state


def _append_apply_operation(
    state: dict[str, Any],
    candidate: dict[str, Any],
    version: dict[str, Any],
) -> None:
    operations = state.setdefault("operations", [])
    if not isinstance(operations, list):
        operations = []
        state["operations"] = operations
    operation = {
        "operation_id": uuid.uuid4().hex[:12],
        "type": "image_edit_apply",
        "label": "替换编辑预览图",
        "scope": "page",
        "page_no": candidate.get("page_no"),
        "instruction": candidate.get("instruction", ""),
        "status": "completed",
        "execution": "direct",
        "message": "已将编辑预览图替换为当前页面图片。",
        "candidate_id": candidate.get("candidate_id", ""),
        "version_id": version.get("version_id", ""),
        "created_at": _timestamp(),
        "updated_at": _timestamp(),
    }
    operations.append(operation)
    del operations[:-job_operations_service.MAX_OPERATION_HISTORY]


def _invalidate_delivery_result(state: dict[str, Any]) -> None:
    state["result"] = {"deliveries": {}, "editable_delivery_bundle": {}}


def _sync_job_snapshot(runtime: Any, job_dir: Path, state: dict[str, Any]) -> None:
    snapshot = runtime.load_job_snapshot(job_dir)
    if not snapshot:
        snapshot = runtime.build_job_payload_from_state(state, {})
    else:
        snapshot = runtime.build_job_payload_from_state(state, snapshot)
    snapshot["pages"] = state.get("pages", [])
    snapshot["reference_pages"] = state.get("reference_pages", [])
    snapshot["element_pages"] = state.get("element_pages", [])
    snapshot["result"] = state.get("result", {})
    snapshot["image_edit_candidates"] = state.get("image_edit_candidates", [])
    runtime.write_job_snapshot(job_dir, snapshot)


def _normalize_preview_type(value: Any) -> str:
    preview_type = str(value or "").strip().lower()
    return preview_type if preview_type in IMAGE_SLOTS else "reference"


def _coerce_page_no(value: Any) -> int:
    try:
        page_no = int(value)
    except (TypeError, ValueError):
        page_no = 0
    if page_no <= 0:
        raise ValueError("缺少有效的 page_no。")
    return page_no


def _normalize_instruction(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_annotations(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    annotations: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            continue
        box = _normalize_box(item.get("box"))
        if box is None:
            continue
        annotations.append(
            {
                "id": _normalize_instruction(item.get("id")) or f"annotation-{index}",
                "label": _normalize_instruction(item.get("label")) or f"区域 {index}",
                "box": box,
            }
        )
    return annotations


def _normalize_box(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    box = {
        "x": _clamp_ratio(value.get("x")),
        "y": _clamp_ratio(value.get("y")),
        "width": _clamp_ratio(value.get("width")),
        "height": _clamp_ratio(value.get("height")),
    }
    if box["width"] <= 0 or box["height"] <= 0:
        return None
    return box


def _clamp_ratio(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return min(1.0, max(0.0, number))


def _format_ratio(value: Any) -> str:
    return f"{_clamp_ratio(value):.4f}"


def _build_image_edit_request_metadata(
    *,
    candidate_id: str,
    job_id: str,
    page_no: int,
    preview_type: str,
    instruction: str,
    annotations: list[dict[str, Any]],
    prompt: str,
    prompt_path: Path,
    metadata_path: Path,
    source_image: str,
    source_path: Path,
    output_path: Path,
    active_config: dict[str, Any],
    image_profile: dict[str, Any],
    image_provider: OpenAIImageProvider,
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "job_id": job_id,
        "page_no": page_no,
        "preview_type": preview_type,
        "preview_label": IMAGE_SLOTS[_normalize_preview_type(preview_type)]["label"],
        "instruction": instruction,
        "annotations": annotations,
        "prompt": prompt,
        "source_image": source_image,
        "source_path": str(source_path),
        "output_path": str(output_path),
        "prompt_path": str(prompt_path),
        "metadata_path": str(metadata_path),
        "image_size": {
            "width": int(active_config.get("image_width", 2048)),
            "height": int(active_config.get("image_height", 1152)),
            "size": str(active_config.get("active_image_size") or active_config.get("image_size") or ""),
        },
        "model_profile": _public_model_profile(image_profile),
        "request_options": _public_image_request_options(image_provider),
        "created_at": _timestamp(),
        "updated_at": _timestamp(),
    }


def _write_image_edit_metadata(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _public_model_profile(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(profile.get("id") or ""),
        "name": str(profile.get("name") or ""),
        "model": str(profile.get("model") or ""),
        "base_url": str(profile.get("base_url") or ""),
    }


def _public_image_request_options(image_provider: OpenAIImageProvider) -> dict[str, Any]:
    return {
        "model": str(getattr(image_provider, "model", "")),
        "base_url": str(getattr(image_provider, "api_base_url", "")),
        "size": str(getattr(image_provider, "size", "")),
        "pixel_size": str(getattr(image_provider, "pixel_size", "")),
        "resolution": str(getattr(image_provider, "resolution", "")),
        "quality": str(getattr(image_provider, "quality", "")),
        "background": str(getattr(image_provider, "background", "")),
        "output_format": str(getattr(image_provider, "output_format", "")),
        "response_format": str(getattr(image_provider, "response_format", "")),
        "moderation": str(getattr(image_provider, "moderation", "")),
        "n": int(getattr(image_provider, "n", 1) or 1),
    }


def _timestamp() -> str:
    return utc_iso_timestamp(timespec="milliseconds")
