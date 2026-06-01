from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ppt_system.export.delivery_options import (
    build_editable_delivery_description,
    build_editable_delivery_label,
    build_editable_delivery_mode,
    normalize_editable_delivery_layer_mode,
)
from ppt_system.export.editable_delivery_bundle import (
    build_editable_delivery_script_path,
    load_editable_delivery_bundle,
)
from ppt_system.export.export_layer_mode import count_output_slides
from ppt_system.export.export_step_checkpoint import build_file_content_signature, stable_hash_payload


CACHE_SCHEMA_VERSION = 1


def load_cached_editable_delivery(
    bundle_path: Path,
    output_pptx: Path,
    *,
    layer_mode: str,
) -> dict[str, Any] | None:
    """读取可编辑 PPT 交付缓存，命中时避免重复重组整套 PPTX。"""
    resolved_layer_mode = normalize_editable_delivery_layer_mode(layer_mode)
    if not output_pptx.exists():
        return None

    signature = build_editable_delivery_cache_signature(
        bundle_path,
        output_pptx,
        layer_mode=resolved_layer_mode,
    )
    metadata_path = build_editable_delivery_cache_path(output_pptx)
    cached_payload = _load_exact_cache_payload(metadata_path, signature=signature)
    if cached_payload is not None:
        return cached_payload

    if _is_existing_output_fresh(bundle_path, output_pptx):
        payload = build_editable_delivery_payload_from_existing_output(
            bundle_path,
            output_pptx,
            layer_mode=resolved_layer_mode,
        )
        save_editable_delivery_cache(
            bundle_path,
            output_pptx,
            layer_mode=resolved_layer_mode,
            export_payload=payload,
        )
        return payload
    return None


def save_editable_delivery_cache(
    bundle_path: Path,
    output_pptx: Path,
    *,
    layer_mode: str,
    export_payload: dict[str, Any],
) -> Path:
    resolved_layer_mode = normalize_editable_delivery_layer_mode(layer_mode)
    signature = build_editable_delivery_cache_signature(
        bundle_path,
        output_pptx,
        layer_mode=resolved_layer_mode,
    )
    metadata_path = build_editable_delivery_cache_path(output_pptx)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "signature": signature,
        "signature_hash": stable_hash_payload(signature),
        "payload": _normalize_export_payload(
            export_payload,
            output_pptx=output_pptx,
            layer_mode=resolved_layer_mode,
        ),
    }
    temp_path = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(metadata_path)
    return metadata_path


def build_editable_delivery_cache_path(output_pptx: Path) -> Path:
    return output_pptx.with_suffix(output_pptx.suffix + ".cache.json")


def build_editable_delivery_cache_signature(
    bundle_path: Path,
    output_pptx: Path,
    *,
    layer_mode: str,
) -> dict[str, Any]:
    resolved_layer_mode = normalize_editable_delivery_layer_mode(layer_mode)
    return {
        "schema_version": CACHE_SCHEMA_VERSION,
        "bundle": build_file_content_signature(bundle_path),
        "layer_mode": resolved_layer_mode,
        "output_pptx": str(output_pptx.resolve()),
    }


def build_editable_delivery_payload_from_existing_output(
    bundle_path: Path,
    output_pptx: Path,
    *,
    layer_mode: str,
) -> dict[str, Any]:
    resolved_layer_mode = normalize_editable_delivery_layer_mode(layer_mode)
    bundle = load_editable_delivery_bundle(bundle_path)
    project = dict(bundle.get("project") or {})
    work_dir = Path(str(bundle.get("work_dir") or "")).resolve()
    logical_page_count = _resolve_logical_page_count(bundle, project)
    return {
        "output_pptx": str(output_pptx),
        "text_script_path": str(build_editable_delivery_script_path(work_dir, resolved_layer_mode)),
        "work_dir": str(work_dir),
        "logical_page_count": logical_page_count,
        "page_count": count_output_slides(logical_page_count, resolved_layer_mode),
        "delivery_mode": build_editable_delivery_mode(resolved_layer_mode),
        "layer_mode": resolved_layer_mode,
        "label": build_editable_delivery_label(resolved_layer_mode),
        "description": build_editable_delivery_description(resolved_layer_mode),
        "assets": dict(bundle.get("assets") or {}),
        "page_results": list(bundle.get("page_results") or []),
    }


def _load_exact_cache_payload(metadata_path: Path, *, signature: dict[str, Any]) -> dict[str, Any] | None:
    if not metadata_path.exists():
        return None
    try:
        cache = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(cache, dict):
        return None
    if int(cache.get("schema_version", 0) or 0) != CACHE_SCHEMA_VERSION:
        return None
    if cache.get("signature") != signature:
        return None
    payload = cache.get("payload")
    return dict(payload) if isinstance(payload, dict) else None


def _normalize_export_payload(
    export_payload: dict[str, Any],
    *,
    output_pptx: Path,
    layer_mode: str,
) -> dict[str, Any]:
    payload = json.loads(json.dumps(export_payload, ensure_ascii=False, default=str))
    payload["output_pptx"] = str(output_pptx)
    payload["layer_mode"] = normalize_editable_delivery_layer_mode(layer_mode)
    return payload


def _is_existing_output_fresh(bundle_path: Path, output_pptx: Path) -> bool:
    try:
        return output_pptx.stat().st_mtime >= bundle_path.stat().st_mtime
    except OSError:
        return False


def _resolve_logical_page_count(bundle: dict[str, Any], project: dict[str, Any]) -> int:
    pages = project.get("pages")
    if isinstance(pages, list):
        return len(pages)
    try:
        return max(0, int(bundle.get("logical_page_count", 0) or 0))
    except (TypeError, ValueError):
        return 0
