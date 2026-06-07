from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ppt_system.export.delivery_options import (
    EDITABLE_PPT_DELIVERY_KEY,
    EDITABLE_SINGLE_PAGE_DELIVERY_ACTION_KEY,
    EDITABLE_SPLIT_PAGES_DELIVERY_ACTION_KEY,
    REFERENCE_PPT_DELIVERY_KEY,
)
from ppt_system.export.export_layer_mode import OVERLAY_LAYER_MODE, SEPARATE_LAYER_MODE
from ppt_system.jobs.job_delivery_state import merge_job_result, normalize_job_result_payload
from ppt_system.web.services.job_state_runtime import (
    extract_element_pages_from_state,
    extract_pages_from_state,
    extract_reference_pages_from_state,
)


RUNTIME_SNAPSHOT_EXTENSION_FIELDS = ("image_edit_candidates",)


def build_job_payload(
    *,
    job_id: str,
    config: dict[str, Any],
    content: str,
    plan: dict[str, Any],
    pages: list[dict[str, Any]],
    references: list[dict[str, Any]],
    element_pages: list[dict[str, Any]],
    chat_provider: Any,
    chat_profile: dict[str, Any],
    image_provider: Any,
    image_profile: dict[str, Any],
    result_payload: dict[str, Any] | None = None,
    runtime_state: dict[str, Any] | None = None,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
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
    return merge_runtime_snapshot_extensions(payload, runtime_state, snapshot)


def write_job_snapshot(job_dir: Path, job_payload: dict[str, Any]) -> None:
    snapshot = load_job_snapshot(job_dir)
    payload = merge_runtime_snapshot_extensions(job_payload, snapshot)
    (job_dir / "job.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
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
    state_plan = state.get("plan", {})
    plan = state_plan if isinstance(state_plan, dict) and state_plan else source.get("plan", {})
    payload = {
        "job_id": str(state.get("job_id") or source.get("job_id") or ""),
        "mode": str(source.get("mode") or ""),
        "content": str(source.get("content") or state.get("job_meta", {}).get("content") or ""),
        "plan": plan,
        "pages": extract_pages_from_state(state),
        "model_profiles": source.get("model_profiles", {}),
        "reference_pages": extract_reference_pages_from_state(state),
        "element_pages": extract_element_pages_from_state(state),
        "result": result_payload,
    }
    return merge_runtime_snapshot_extensions(payload, state, source)


def merge_runtime_snapshot_extensions(
    payload: dict[str, Any],
    *sources: dict[str, Any] | None,
) -> dict[str, Any]:
    """保留不参与核心生成流程、但用户操作历史需要展示的运行态扩展字段。"""
    result = dict(payload)
    for field in RUNTIME_SNAPSHOT_EXTENSION_FIELDS:
        if field in result:
            continue
        for source in sources:
            if isinstance(source, dict) and field in source:
                result[field] = json.loads(json.dumps(source[field], ensure_ascii=False))
                break
    return result


def resolve_delivery_action_layer_mode(delivery_key: str, payload: dict[str, Any]) -> str:
    if delivery_key == EDITABLE_SINGLE_PAGE_DELIVERY_ACTION_KEY:
        return OVERLAY_LAYER_MODE
    if delivery_key == EDITABLE_SPLIT_PAGES_DELIVERY_ACTION_KEY:
        return SEPARATE_LAYER_MODE
    if delivery_key == EDITABLE_PPT_DELIVERY_KEY:
        return str(payload.get("layer_mode", "")).strip()
    if delivery_key == REFERENCE_PPT_DELIVERY_KEY:
        return ""
    return ""
