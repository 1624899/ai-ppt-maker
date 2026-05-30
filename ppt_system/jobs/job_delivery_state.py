from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ppt_system.export.delivery_options import (
    EDITABLE_PPT_DELIVERY_KEY,
    REFERENCE_PPT_DELIVERY_KEY,
    build_editable_delivery_description,
    build_editable_delivery_label,
    normalize_editable_delivery_layer_mode,
)
from ppt_system.export.export_layer_mode import OVERLAY_LAYER_MODE, SEPARATE_LAYER_MODE


REFERENCE_DELIVERY_MODE = "reference_only"


def clone_payload(payload: Any) -> Any:
    return json.loads(json.dumps(payload, ensure_ascii=False))


def normalize_job_result_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    normalized = clone_payload(payload)
    deliveries = normalized.get("deliveries")
    if not isinstance(deliveries, dict):
        normalized["deliveries"] = {}
    editable_bundle = normalized.get("editable_delivery_bundle")
    if editable_bundle is None:
        normalized["editable_delivery_bundle"] = {}
    elif not isinstance(editable_bundle, dict):
        normalized["editable_delivery_bundle"] = {}
    return normalized


def merge_job_result(existing_payload: Any, next_payload: Any) -> dict[str, Any]:
    existing = normalize_job_result_payload(existing_payload)
    next_result = normalize_job_result_payload(next_payload)
    merged = clone_payload(existing)
    merged.update(next_result)
    merged["deliveries"] = _merge_delivery_store(
        existing.get("deliveries"),
        next_result.get("deliveries"),
    )
    if not merged.get("editable_delivery_bundle") and isinstance(existing.get("editable_delivery_bundle"), dict):
        merged["editable_delivery_bundle"] = clone_payload(existing["editable_delivery_bundle"])
    return merged


def get_delivery_store(result_payload: Any) -> dict[str, Any]:
    result = normalize_job_result_payload(result_payload)
    deliveries = result.get("deliveries")
    if not isinstance(deliveries, dict):
        return {}
    return deliveries


def get_reference_delivery(result_payload: Any) -> dict[str, Any]:
    deliveries = get_delivery_store(result_payload)
    item = deliveries.get(REFERENCE_PPT_DELIVERY_KEY)
    return clone_payload(item) if isinstance(item, dict) else {}


def get_editable_delivery_store(result_payload: Any) -> dict[str, Any]:
    deliveries = get_delivery_store(result_payload)
    item = deliveries.get(EDITABLE_PPT_DELIVERY_KEY)
    if not isinstance(item, dict):
        return {"latest": {}, "by_layer_mode": {}}
    latest = item.get("latest")
    by_layer_mode = item.get("by_layer_mode")
    return {
        "latest": clone_payload(latest) if isinstance(latest, dict) else {},
        "by_layer_mode": clone_payload(by_layer_mode) if isinstance(by_layer_mode, dict) else {},
    }


def set_reference_delivery(result_payload: Any, delivery_payload: dict[str, Any]) -> dict[str, Any]:
    result = normalize_job_result_payload(result_payload)
    result.setdefault("deliveries", {})
    result["deliveries"][REFERENCE_PPT_DELIVERY_KEY] = clone_payload(delivery_payload)
    return result


def set_editable_delivery(
    result_payload: Any,
    delivery_payload: dict[str, Any],
    *,
    layer_mode: Any,
) -> dict[str, Any]:
    resolved_layer_mode = normalize_editable_delivery_layer_mode(layer_mode)
    result = normalize_job_result_payload(result_payload)
    deliveries = result.setdefault("deliveries", {})
    editable_store = deliveries.get(EDITABLE_PPT_DELIVERY_KEY)
    if not isinstance(editable_store, dict):
        editable_store = {}
    by_layer_mode = editable_store.get("by_layer_mode")
    if not isinstance(by_layer_mode, dict):
        by_layer_mode = {}
    cloned_payload = clone_payload(delivery_payload)
    by_layer_mode[resolved_layer_mode] = cloned_payload
    editable_store["latest"] = cloned_payload
    editable_store["by_layer_mode"] = by_layer_mode
    deliveries[EDITABLE_PPT_DELIVERY_KEY] = editable_store
    return result


def set_editable_delivery_bundle(result_payload: Any, bundle_payload: dict[str, Any]) -> dict[str, Any]:
    result = normalize_job_result_payload(result_payload)
    result["editable_delivery_bundle"] = clone_payload(bundle_payload)
    return result


def get_editable_delivery_bundle(result_payload: Any) -> dict[str, Any]:
    result = normalize_job_result_payload(result_payload)
    bundle = result.get("editable_delivery_bundle")
    return clone_payload(bundle) if isinstance(bundle, dict) else {}


def build_reference_delivery_payload(
    job_id: str,
    job_dir: Path,
    output_pptx: Path,
    *,
    page_count: int,
    logical_page_count: int,
) -> dict[str, Any]:
    return {
        "key": REFERENCE_PPT_DELIVERY_KEY,
        "label": "图片PPT",
        "description": "按当前原稿图原样导出的图片版 PPT。",
        "pptx_path": str(output_pptx),
        "pptx_url": build_run_file_url(job_id, job_dir, output_pptx),
        "page_count": int(page_count),
        "logical_page_count": int(logical_page_count),
        "delivery_mode": REFERENCE_DELIVERY_MODE,
        "generated_at": build_generated_timestamp(),
    }


def build_editable_delivery_payload(
    job_id: str,
    job_dir: Path,
    export_payload: dict[str, Any],
) -> dict[str, Any]:
    output_pptx = Path(str(export_payload.get("output_pptx", "")).strip())
    if not output_pptx:
        raise ValueError("可编辑 PPT 导出结果缺少输出路径。")
    payload = clone_payload(export_payload)
    payload["key"] = EDITABLE_PPT_DELIVERY_KEY
    payload["label"] = str(payload.get("label") or build_editable_delivery_label(payload.get("layer_mode")))
    payload["description"] = str(
        payload.get("description") or build_editable_delivery_description(payload.get("layer_mode"))
    )
    payload["pptx_path"] = str(output_pptx)
    payload["pptx_url"] = build_run_file_url(job_id, job_dir, output_pptx)
    payload["generated_at"] = build_generated_timestamp()
    return payload


def build_delivery_actions(job_state: dict[str, Any], job_dir: Path) -> list[dict[str, Any]]:
    result_payload = normalize_job_result_payload(job_state.get("result"))
    job_id = str(job_state.get("job_id") or job_dir.name)
    pages = _extract_pages(job_state)
    reference_pages = _extract_reference_pages(job_state)
    status = str(job_state.get("status", "")).strip()
    reference_ready = bool(reference_pages) and (
        _is_stage_completed(job_state, "reference_generation") or status == "completed"
    )
    editable_bundle = get_editable_delivery_bundle(result_payload)
    editable_bundle_path = Path(str(editable_bundle.get("bundle_path", "")).strip()) if editable_bundle else None
    editable_ready = bool(editable_bundle) and editable_bundle_path is not None and editable_bundle_path.exists()
    reference_delivery = get_reference_delivery(result_payload)
    editable_delivery_store = get_editable_delivery_store(result_payload)

    actions: list[dict[str, Any]] = []
    if reference_ready:
        actions.append(
            {
                "key": REFERENCE_PPT_DELIVERY_KEY,
                "label": "图片PPT生成",
                "description": "使用当前原稿图导出图片版 PPT，适合保留原始视觉效果。",
                "visible": True,
                "generated": bool(reference_delivery),
                "generated_file": reference_delivery,
                "logical_page_count": len(reference_pages),
                "page_count": len(reference_pages),
            }
        )
    if editable_ready:
        latest_editable_delivery = editable_delivery_store.get("latest", {})
        actions.append(
            {
                "key": EDITABLE_PPT_DELIVERY_KEY,
                "label": "可编辑PPT生成",
                "description": "使用已生成的可编辑元素和文字脚本导出 PPT，可选择双页或合页。",
                "visible": True,
                "generated": bool(latest_editable_delivery),
                "generated_file": latest_editable_delivery,
                "logical_page_count": int(editable_bundle.get("logical_page_count", len(pages))),
                "page_count": int(latest_editable_delivery.get("page_count", 0) or 0),
                "options": [
                    {
                        "layer_mode": SEPARATE_LAYER_MODE,
                        "label": build_editable_delivery_label(SEPARATE_LAYER_MODE),
                        "description": build_editable_delivery_description(SEPARATE_LAYER_MODE),
                    },
                    {
                        "layer_mode": OVERLAY_LAYER_MODE,
                        "label": build_editable_delivery_label(OVERLAY_LAYER_MODE),
                        "description": build_editable_delivery_description(OVERLAY_LAYER_MODE),
                    },
                ],
            }
        )
    return actions


def attach_delivery_actions(job_state: dict[str, Any], job_dir: Path) -> dict[str, Any]:
    state = clone_payload(job_state)
    state["delivery_actions"] = build_delivery_actions(state, job_dir)
    return state


def build_run_file_url(job_id: str, job_dir: Path, file_path: Path) -> str:
    return f"/runs/{job_id}/{file_path.relative_to(job_dir).as_posix()}"


def build_generated_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _merge_delivery_store(existing_payload: Any, next_payload: Any) -> dict[str, Any]:
    existing = clone_payload(existing_payload) if isinstance(existing_payload, dict) else {}
    next_deliveries = clone_payload(next_payload) if isinstance(next_payload, dict) else {}
    merged = existing
    merged.update(next_deliveries)
    existing_editable = existing.get(EDITABLE_PPT_DELIVERY_KEY)
    next_editable = next_deliveries.get(EDITABLE_PPT_DELIVERY_KEY)
    merged[EDITABLE_PPT_DELIVERY_KEY] = _merge_editable_delivery_store(existing_editable, next_editable)
    return merged


def _merge_editable_delivery_store(existing_payload: Any, next_payload: Any) -> dict[str, Any]:
    existing = clone_payload(existing_payload) if isinstance(existing_payload, dict) else {}
    next_store = clone_payload(next_payload) if isinstance(next_payload, dict) else {}
    merged = existing
    merged.update(next_store)
    existing_by_mode = existing.get("by_layer_mode")
    next_by_mode = next_store.get("by_layer_mode")
    merged_by_mode = clone_payload(existing_by_mode) if isinstance(existing_by_mode, dict) else {}
    if isinstance(next_by_mode, dict):
        merged_by_mode.update(next_by_mode)
    merged["by_layer_mode"] = merged_by_mode
    if not isinstance(merged.get("latest"), dict) and isinstance(existing.get("latest"), dict):
        merged["latest"] = clone_payload(existing["latest"])
    return merged


def _extract_pages(job_state: dict[str, Any]) -> list[dict[str, Any]]:
    pages = job_state.get("pages", [])
    return list(pages) if isinstance(pages, list) else []


def _extract_reference_pages(job_state: dict[str, Any]) -> list[dict[str, Any]]:
    reference_pages = job_state.get("reference_pages", [])
    if isinstance(reference_pages, list) and reference_pages:
        return list(reference_pages)
    rebuilt: list[dict[str, Any]] = []
    for page in _extract_pages(job_state):
        image_ref = str(page.get("reference_image", "")).strip()
        if not image_ref:
            continue
        rebuilt.append({"page_no": page.get("page_no"), "image": image_ref})
    return rebuilt


def _is_stage_completed(job_state: dict[str, Any], stage_key: str) -> bool:
    stages = job_state.get("stages", [])
    if not isinstance(stages, list):
        return False
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        if str(stage.get("key", "")).strip() != stage_key:
            continue
        return str(stage.get("status", "")).strip() == "completed"
    return False
