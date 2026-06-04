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
) -> dict[str, Any]:
    return {
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


def write_job_snapshot(job_dir: Path, job_payload: dict[str, Any]) -> None:
    (job_dir / "job.json").write_text(
        json.dumps(job_payload, ensure_ascii=False, indent=2),
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
    return {
        "job_id": str(state.get("job_id") or source.get("job_id") or ""),
        "mode": str(source.get("mode") or ""),
        "content": str(source.get("content") or state.get("job_meta", {}).get("content") or ""),
        "plan": source.get("plan", state.get("plan", {})),
        "pages": source.get("pages", extract_pages_from_state(state)),
        "model_profiles": source.get("model_profiles", {}),
        "reference_pages": source.get("reference_pages", extract_reference_pages_from_state(state)),
        "element_pages": source.get("element_pages", extract_element_pages_from_state(state)),
        "result": result_payload,
    }


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
