from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from flask import jsonify, request

from ppt_system.web.runtime import get_runtime_module
from ppt_system.web.services.job_edit_planner import (
    apply_job_style_edit,
    apply_page_layout_edit,
    apply_page_text_edit,
    build_edit_context,
    plan_agent_edit,
)
from ppt_system.web.services.job_submission_runtime import submit_existing_job_pipeline


RUNNING_STATUSES = {"queued", "running", "stopping"}
MAX_OPERATION_HISTORY = 80

PIPELINE_OPERATION_TYPES = {"page_regenerate", "restore_page_version"}
PAGE_RECORD_ONLY_TYPES = {"page_text_optimize", "page_layout_optimize"}
JOB_RECORD_ONLY_TYPES = {"agent_instruction", "job_style_adjust"}

OPERATION_LABELS = {
    "agent_instruction": "Agent 修改请求",
    "job_style_adjust": "整套风格调整",
    "page_regenerate": "重新生成本页",
    "page_text_optimize": "仅优化文字",
    "page_layout_optimize": "仅优化排版",
    "restore_page_version": "恢复页面版本",
}

RECORD_ONLY_MESSAGE = "已记录修改意图，等待 Agent 编辑流水线接入后执行。"
AGENT_EDIT_MESSAGE = "已应用编辑意图，并提交后续生成流水线。"
TEXT_EDIT_MESSAGE = "已更新页面文字结构，并提交可编辑 PPT 重建。"


def api_create_job_operation(job_id: str):
    payload = request.get_json(silent=True) or {}
    try:
        state = create_job_operation(job_id, payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify(state)


def create_job_operation(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    runtime = get_runtime_module()
    record = runtime.get_job_record(runtime.JOBS_DB_PATH, job_id)
    if not record:
        raise FileNotFoundError("任务不存在")
    operation_type = _normalize_operation_type(payload.get("operation_type") or payload.get("type"))
    job_dir = Path(record["job_dir"])
    state, _ = runtime.get_job_state_snapshot(job_id, job_dir)
    if not state:
        raise FileNotFoundError("任务状态不存在")

    if operation_type == "page_regenerate":
        _ensure_not_running(record)
        return _regenerate_page(runtime, record, state, payload)
    if operation_type == "restore_page_version":
        _ensure_not_running(record)
        return _restore_page_version(runtime, record, state, payload)
    if operation_type in PAGE_RECORD_ONLY_TYPES | JOB_RECORD_ONLY_TYPES:
        return _apply_agent_edit_operation(runtime, record, state, payload, operation_type)
    return _record_pending_operation(runtime, record, state, payload, operation_type)


def _normalize_operation_type(value: Any) -> str:
    operation_type = str(value or "").strip()
    allowed = PIPELINE_OPERATION_TYPES | PAGE_RECORD_ONLY_TYPES | JOB_RECORD_ONLY_TYPES
    if operation_type not in allowed:
        raise ValueError(f"不支持的任务操作：{operation_type or '空'}")
    return operation_type


def _ensure_not_running(record: dict[str, Any]) -> None:
    if str(record.get("status")) in RUNNING_STATUSES:
        raise RuntimeError("当前任务正在运行，请等待完成或停止后再操作。")


def _apply_agent_edit_operation(
    runtime: Any,
    record: dict[str, Any],
    state: dict[str, Any],
    payload: dict[str, Any],
    operation_type: str,
) -> dict[str, Any]:
    job_id = str(record["job_id"])
    job_dir = Path(record["job_dir"])
    page_no = _optional_page_no(payload.get("page_no"))
    if operation_type in PAGE_RECORD_ONLY_TYPES:
        if page_no is None:
            raise ValueError("页面级操作缺少 page_no。")
        _find_page(state, page_no)
    instruction = _normalize_instruction(payload.get("instruction"))
    if not instruction:
        raise ValueError("请先填写修改要求。")

    available_page_numbers = _collect_page_numbers(state)
    edit_plan = plan_agent_edit(
        operation_type,
        instruction,
        explicit_page_no=page_no,
        available_page_numbers=available_page_numbers,
    )
    if edit_plan.record_only:
        return _record_pending_operation(runtime, record, state, payload, operation_type)
    if not edit_plan.page_numbers:
        return _record_pending_operation(runtime, record, state, payload, operation_type)

    _ensure_not_running(record)
    for target_page_no in edit_plan.page_numbers:
        _find_page(state, target_page_no)

    operation = _build_operation(operation_type, page_no=page_no, instruction=instruction, payload=payload)
    operation["status"] = "submitted"
    operation["execution"] = "pipeline"
    operation["edit_kind"] = edit_plan.edit_kind
    operation["affected_pages"] = list(edit_plan.page_numbers)
    operation["message"] = TEXT_EDIT_MESSAGE if edit_plan.edit_kind == "text" else AGENT_EDIT_MESSAGE
    versions = [
        _create_page_version(job_id, job_dir, state, target_page_no, operation["operation_id"], reason=f"before_{edit_plan.edit_kind}_edit")
        for target_page_no in edit_plan.page_numbers
    ]
    operation["version_ids"] = [version["version_id"] for version in versions]
    if len(versions) == 1:
        operation["version_id"] = versions[0]["version_id"]

    def updater(current_state: dict[str, Any]) -> None:
        context = build_edit_context(current_state)
        effects: list[dict[str, Any]] = []
        _append_operation(current_state, operation)
        for version in versions:
            _append_page_version(current_state, version)
        for target_page_no in edit_plan.page_numbers:
            _append_page_edit_request(current_state, target_page_no, operation)
            if edit_plan.edit_kind == "text":
                effects.append(apply_page_text_edit(current_state, target_page_no, instruction, payload, context))
            elif edit_plan.edit_kind == "layout":
                effects.append(apply_page_layout_edit(current_state, target_page_no, instruction, payload, context))
            elif edit_plan.edit_kind == "style":
                # 整套风格调整只需要执行一次，循环外统一处理。
                continue
            if edit_plan.requires_image_regeneration:
                _invalidate_page_outputs(current_state, target_page_no, "")
        if edit_plan.edit_kind == "style":
            effect = apply_job_style_edit(current_state, instruction, context)
            effects.append(effect)
            for target_page_no in edit_plan.page_numbers:
                _invalidate_page_outputs(current_state, target_page_no, "")
        _update_operation_fields(
            current_state,
            operation["operation_id"],
            {
                "effects": effects,
                "updated_at": _timestamp(),
            },
        )
        _invalidate_delivery_result(current_state)
        if edit_plan.requires_image_regeneration:
            _reset_generation_stages_for_pages(current_state, edit_plan.page_numbers, "等待 Agent 编辑后重新生成")
        else:
            _reset_export_stage(current_state, edit_plan.page_numbers, "等待 Agent 编辑后重建可编辑 PPT")

    updated_state = runtime.mutate_job_state(job_dir, job_id, updater)
    runtime.update_job_record(runtime.JOBS_DB_PATH, job_id, stop_requested=False, status="queued", result={})
    _invalidate_job_snapshot_result(runtime, job_dir)
    submit_existing_job_pipeline(record)
    return runtime.attach_delivery_actions(updated_state, job_dir)


def _regenerate_page(
    runtime: Any,
    record: dict[str, Any],
    state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    job_id = str(record["job_id"])
    job_dir = Path(record["job_dir"])
    page_no = _coerce_page_no(payload.get("page_no"))
    _find_page(state, page_no)
    instruction = _normalize_instruction(payload.get("instruction"))
    operation = _build_operation("page_regenerate", page_no=page_no, instruction=instruction, payload=payload)
    version = _create_page_version(job_id, job_dir, state, page_no, operation["operation_id"], reason="before_regenerate")
    operation["version_id"] = version["version_id"]
    operation["status"] = "submitted"
    operation["message"] = "已提交单页重新生成，将复用现有流水线补齐该页并重建导出结果。"

    def updater(current_state: dict[str, Any]) -> None:
        _append_operation(current_state, operation)
        _append_page_version(current_state, version)
        _append_page_edit_request(current_state, page_no, operation)
        _invalidate_page_outputs(current_state, page_no, instruction)
        _invalidate_delivery_result(current_state)
        _reset_generation_stages(current_state, page_no, "等待重新生成本页")

    updated_state = runtime.mutate_job_state(job_dir, job_id, updater)
    runtime.update_job_record(runtime.JOBS_DB_PATH, job_id, stop_requested=False, status="queued", result={})
    _invalidate_job_snapshot_result(runtime, job_dir)
    submit_existing_job_pipeline(record)
    return runtime.attach_delivery_actions(updated_state, job_dir)


def _restore_page_version(
    runtime: Any,
    record: dict[str, Any],
    state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    job_id = str(record["job_id"])
    job_dir = Path(record["job_dir"])
    page_no = _coerce_page_no(payload.get("page_no"))
    _find_page(state, page_no)
    version = _find_page_version(state, page_no, payload.get("version_id"))
    operation = _build_operation(
        "restore_page_version",
        page_no=page_no,
        instruction=_normalize_instruction(payload.get("instruction")),
        payload={**payload, "version_id": version["version_id"]},
    )
    rollback_version = _create_page_version(job_id, job_dir, state, page_no, operation["operation_id"], reason="before_restore")
    operation["status"] = "submitted"
    operation["message"] = "已恢复页面版本，并提交导出结果重建。"
    operation["version_id"] = version["version_id"]
    operation["rollback_version_id"] = rollback_version["version_id"]

    def updater(current_state: dict[str, Any]) -> None:
        _append_operation(current_state, operation)
        _append_page_version(current_state, rollback_version)
        _restore_page_from_version(current_state, version)
        _invalidate_delivery_result(current_state)
        _reset_generation_stages(current_state, page_no, "等待基于已恢复版本重建导出")

    updated_state = runtime.mutate_job_state(job_dir, job_id, updater)
    runtime.update_job_record(runtime.JOBS_DB_PATH, job_id, stop_requested=False, status="queued", result={})
    _invalidate_job_snapshot_result(runtime, job_dir)
    submit_existing_job_pipeline(record)
    return runtime.attach_delivery_actions(updated_state, job_dir)


def _record_pending_operation(
    runtime: Any,
    record: dict[str, Any],
    state: dict[str, Any],
    payload: dict[str, Any],
    operation_type: str,
) -> dict[str, Any]:
    job_id = str(record["job_id"])
    job_dir = Path(record["job_dir"])
    page_no = _optional_page_no(payload.get("page_no"))
    if operation_type in PAGE_RECORD_ONLY_TYPES:
        if page_no is None:
            raise ValueError("页面级操作缺少 page_no。")
        _find_page(state, page_no)
    instruction = _normalize_instruction(payload.get("instruction"))
    if not instruction and operation_type in JOB_RECORD_ONLY_TYPES | PAGE_RECORD_ONLY_TYPES:
        raise ValueError("请先填写修改要求。")

    operation = _build_operation(operation_type, page_no=page_no, instruction=instruction, payload=payload)
    operation["status"] = "accepted"
    operation["execution"] = "pending_backend"
    operation["message"] = RECORD_ONLY_MESSAGE

    def updater(current_state: dict[str, Any]) -> None:
        _append_operation(current_state, operation)
        if page_no is not None:
            _append_page_edit_request(current_state, page_no, operation)

    updated_state = runtime.mutate_job_state(job_dir, job_id, updater)
    refreshed_state, _ = runtime.get_job_state_snapshot(job_id, job_dir)
    return refreshed_state or updated_state


def _build_operation(
    operation_type: str,
    *,
    page_no: int | None,
    instruction: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    now = _timestamp()
    operation: dict[str, Any] = {
        "operation_id": uuid.uuid4().hex[:12],
        "type": operation_type,
        "label": OPERATION_LABELS[operation_type],
        "scope": "page" if page_no is not None else "job",
        "page_no": page_no,
        "instruction": instruction,
        "payload": _sanitize_payload(payload),
        "status": "created",
        "execution": "pipeline" if operation_type in PIPELINE_OPERATION_TYPES else "pending_backend",
        "message": "",
        "created_at": now,
        "updated_at": now,
    }
    return operation


def _append_operation(state: dict[str, Any], operation: dict[str, Any]) -> None:
    operations = state.setdefault("operations", [])
    if not isinstance(operations, list):
        operations = []
        state["operations"] = operations
    operations.append(json.loads(json.dumps(operation, ensure_ascii=False)))
    del operations[:-MAX_OPERATION_HISTORY]


def _append_page_edit_request(state: dict[str, Any], page_no: int, operation: dict[str, Any]) -> None:
    page = _find_page(state, page_no)
    requests = page.setdefault("edit_requests", [])
    if not isinstance(requests, list):
        requests = []
        page["edit_requests"] = requests
    requests.append(
        {
            "operation_id": operation["operation_id"],
            "type": operation["type"],
            "label": operation["label"],
            "instruction": operation["instruction"],
            "status": operation["status"],
            "created_at": operation["created_at"],
        }
    )
    del requests[:-20]


def _update_operation_fields(state: dict[str, Any], operation_id: str, fields: dict[str, Any]) -> None:
    operations = state.get("operations", [])
    if not isinstance(operations, list):
        return
    for operation in operations:
        if not isinstance(operation, dict) or str(operation.get("operation_id", "")) != str(operation_id):
            continue
        operation.update(json.loads(json.dumps(fields, ensure_ascii=False)))
        return


def _create_page_version(
    job_id: str,
    job_dir: Path,
    state: dict[str, Any],
    page_no: int,
    operation_id: str,
    *,
    reason: str,
) -> dict[str, Any]:
    page = _find_page(state, page_no)
    reference_artifact = _find_artifact(state.get("reference_pages"), page_no)
    element_artifact = _find_artifact(state.get("element_pages"), page_no)
    version_id = uuid.uuid4().hex[:12]
    version_dir = job_dir / "versions" / f"page_{page_no:02d}" / version_id
    version_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "reference": _copy_artifact(job_id, job_dir, version_dir, reference_artifact.get("image") or page.get("reference_image"), "reference"),
        "element": _copy_artifact(job_id, job_dir, version_dir, element_artifact.get("image") or page.get("element_image"), "element"),
    }
    return {
        "version_id": version_id,
        "page_no": page_no,
        "operation_id": operation_id,
        "reason": reason,
        "created_at": _timestamp(),
        "page": json.loads(json.dumps(page, ensure_ascii=False)),
        "reference_artifact": json.loads(json.dumps(reference_artifact, ensure_ascii=False)),
        "element_artifact": json.loads(json.dumps(element_artifact, ensure_ascii=False)),
        "artifacts": artifacts,
    }


def _append_page_version(state: dict[str, Any], version: dict[str, Any]) -> None:
    versions = state.setdefault("page_versions", [])
    if not isinstance(versions, list):
        versions = []
        state["page_versions"] = versions
    versions.append(json.loads(json.dumps(version, ensure_ascii=False)))
    del versions[:-MAX_OPERATION_HISTORY]


def _find_page_version(state: dict[str, Any], page_no: int, version_id: Any) -> dict[str, Any]:
    versions = [item for item in state.get("page_versions", []) if isinstance(item, dict) and int(item.get("page_no", 0) or 0) == page_no]
    if not versions:
        raise ValueError(f"第 {page_no} 页还没有可恢复的版本。")
    requested = str(version_id or "").strip()
    if requested:
        for version in versions:
            if str(version.get("version_id", "")) == requested:
                return version
        raise ValueError(f"找不到页面版本：{requested}")
    return versions[-1]


def _restore_page_from_version(state: dict[str, Any], version: dict[str, Any]) -> None:
    page_no = int(version["page_no"])
    restored_page = json.loads(json.dumps(version.get("page", {}), ensure_ascii=False))
    artifacts = version.get("artifacts", {}) if isinstance(version.get("artifacts"), dict) else {}
    reference_image = _restored_artifact_image(artifacts.get("reference"), version.get("reference_artifact"))
    element_image = _restored_artifact_image(artifacts.get("element"), version.get("element_artifact"))
    restored_page["page_no"] = page_no
    if reference_image:
        restored_page["reference_image"] = reference_image
    if element_image:
        restored_page["element_image"] = element_image
    restored_page["status"] = "completed" if element_image else ("reference_done" if reference_image else restored_page.get("status", "planned"))

    pages = state.setdefault("pages", [])
    for index, page in enumerate(pages):
        if int(page.get("page_no", 0) or 0) == page_no:
            pages[index] = restored_page
            break
    else:
        pages.append(restored_page)
        pages.sort(key=lambda item: int(item.get("page_no", 0) or 0))

    if reference_image:
        reference_artifact = dict(version.get("reference_artifact") or {})
        reference_artifact["page_no"] = page_no
        reference_artifact["image"] = reference_image
        _upsert_artifact(state, "reference_pages", reference_artifact)
    else:
        _remove_artifact(state, "reference_pages", page_no)

    if element_image:
        element_artifact = dict(version.get("element_artifact") or {})
        element_artifact["page_no"] = page_no
        element_artifact["image"] = element_image
        _upsert_artifact(state, "element_pages", element_artifact)
    else:
        _remove_artifact(state, "element_pages", page_no)


def _invalidate_page_outputs(state: dict[str, Any], page_no: int, instruction: str) -> None:
    page = _find_page(state, page_no)
    page["status"] = "planned"
    page["reference_image"] = ""
    page["element_image"] = ""
    if instruction:
        page["reference_prompt"] = _append_instruction_to_prompt(page.get("reference_prompt"), instruction)
        page["elements_prompt"] = _append_instruction_to_prompt(page.get("elements_prompt"), instruction)
    _remove_artifact(state, "reference_pages", page_no)
    _remove_artifact(state, "element_pages", page_no)


def _reset_generation_stages(state: dict[str, Any], page_no: int, summary: str) -> None:
    _reset_generation_stages_for_pages(state, (page_no,), summary)


def _reset_generation_stages_for_pages(state: dict[str, Any], page_numbers: tuple[int, ...], summary: str) -> None:
    state["status"] = "queued"
    state["current_stage"] = "reference_generation"
    state["error"] = ""
    state["stop_requested"] = False
    job_target = str(state.get("job_meta", {}).get("job_target", "editable_ppt"))
    affected_stages = {"reference_generation"}
    if job_target != "reference_only":
        affected_stages.update({"elements_generation", "ppt_export"})
    for stage in state.get("stages", []):
        if not isinstance(stage, dict) or stage.get("key") not in affected_stages:
            continue
        stage["status"] = "pending"
        stage["summary"] = summary
        logs = stage.setdefault("logs", [])
        logs.append(f"{_format_page_scope(page_numbers)}已提交编辑操作，等待流水线处理")


def _reset_export_stage(state: dict[str, Any], page_numbers: tuple[int, ...], summary: str) -> None:
    state["status"] = "queued"
    state["current_stage"] = "ppt_export"
    state["error"] = ""
    state["stop_requested"] = False
    for stage in state.get("stages", []):
        if not isinstance(stage, dict) or stage.get("key") != "ppt_export":
            continue
        stage["status"] = "pending"
        stage["summary"] = summary
        logs = stage.setdefault("logs", [])
        logs.append(f"{_format_page_scope(page_numbers)}已更新文字内容，等待重建可编辑 PPT")


def _format_page_scope(page_numbers: tuple[int, ...]) -> str:
    normalized = [int(page_no) for page_no in page_numbers if int(page_no) > 0]
    if not normalized:
        return "任务"
    if len(normalized) == 1:
        return f"第 {normalized[0]} 页"
    preview = "、".join(str(page_no) for page_no in normalized[:6])
    suffix = "等页面" if len(normalized) > 6 else "页"
    return f"第 {preview} {suffix}"


def _invalidate_delivery_result(state: dict[str, Any]) -> None:
    state["result"] = {"deliveries": {}, "editable_delivery_bundle": {}}


def _invalidate_job_snapshot_result(runtime: Any, job_dir: Path) -> None:
    snapshot = runtime.load_job_snapshot(job_dir)
    if not snapshot:
        return
    snapshot["result"] = {"deliveries": {}, "editable_delivery_bundle": {}}
    runtime.write_job_snapshot(job_dir, snapshot)


def _copy_artifact(
    job_id: str,
    job_dir: Path,
    version_dir: Path,
    image_ref: Any,
    slot: str,
) -> dict[str, Any]:
    source_ref = str(image_ref or "").strip()
    if not source_ref:
        return {"source_image": "", "image": "", "exists": False}
    source = _resolve_artifact_path(job_dir, source_ref)
    if not source.exists() or not source.is_file():
        return {"source_image": source_ref, "image": "", "exists": False}
    suffix = source.suffix or ".png"
    target = version_dir / f"{slot}{suffix}"
    shutil.copy2(source, target)
    return {
        "source_image": source_ref,
        "image": f"/runs/{job_id}/{target.relative_to(job_dir).as_posix()}",
        "path": str(target),
        "exists": True,
    }


def _resolve_artifact_path(job_dir: Path, image_ref: str) -> Path:
    candidate = Path(str(image_ref).strip())
    if candidate.is_absolute():
        return candidate
    normalized = str(image_ref).lstrip("/\\")
    parts = Path(normalized).parts
    if len(parts) >= 3 and parts[0] == "runs":
        return job_dir / Path(*parts[2:])
    return job_dir / normalized


def _restored_artifact_image(artifact_copy: Any, original_artifact: Any) -> str:
    if isinstance(artifact_copy, dict) and artifact_copy.get("image"):
        return str(artifact_copy["image"])
    if isinstance(original_artifact, dict):
        return str(original_artifact.get("image") or "")
    return ""


def _upsert_artifact(state: dict[str, Any], collection_name: str, artifact: dict[str, Any]) -> None:
    page_no = int(artifact["page_no"])
    collection = state.setdefault(collection_name, [])
    if not isinstance(collection, list):
        collection = []
        state[collection_name] = collection
    for index, item in enumerate(collection):
        if isinstance(item, dict) and int(item.get("page_no", 0) or 0) == page_no:
            collection[index] = artifact
            break
    else:
        collection.append(artifact)
    collection.sort(key=lambda item: int(item.get("page_no", 0) or 0))


def _remove_artifact(state: dict[str, Any], collection_name: str, page_no: int) -> None:
    collection = state.get(collection_name, [])
    if not isinstance(collection, list):
        state[collection_name] = []
        return
    state[collection_name] = [
        item for item in collection if not isinstance(item, dict) or int(item.get("page_no", 0) or 0) != int(page_no)
    ]


def _find_artifact(collection: Any, page_no: int) -> dict[str, Any]:
    if not isinstance(collection, list):
        return {}
    for item in collection:
        if isinstance(item, dict) and int(item.get("page_no", 0) or 0) == int(page_no):
            return item
    return {}


def _find_page(state: dict[str, Any], page_no: int) -> dict[str, Any]:
    for page in state.get("pages", []):
        if isinstance(page, dict) and int(page.get("page_no", 0) or 0) == int(page_no):
            return page
    raise ValueError(f"找不到第 {page_no} 页。")


def _collect_page_numbers(state: dict[str, Any]) -> list[int]:
    page_numbers: list[int] = []
    for page in state.get("pages", []):
        if not isinstance(page, dict):
            continue
        try:
            page_no = int(page.get("page_no", 0) or 0)
        except (TypeError, ValueError):
            continue
        if page_no > 0 and page_no not in page_numbers:
            page_numbers.append(page_no)
    page_numbers.sort()
    return page_numbers


def _coerce_page_no(value: Any) -> int:
    page_no = _optional_page_no(value)
    if page_no is None:
        raise ValueError("缺少有效的 page_no。")
    return page_no


def _optional_page_no(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        page_no = int(value)
    except (TypeError, ValueError):
        return None
    return page_no if page_no > 0 else None


def _normalize_instruction(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _append_instruction_to_prompt(prompt: Any, instruction: str) -> str:
    current = str(prompt or "").strip()
    addition = f"本次单页修改要求：{instruction}"
    if not current:
        return addition
    if addition in current:
        return current
    return f"{current}\n\n{addition}"


def _sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in payload.items():
        if key in {"operation_type", "type", "page_no", "instruction", "version_id", "source"}:
            sanitized[key] = value
    return sanitized


def _timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
