from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ppt_system.export.text_script_runtime import normalize_asset_adjustments, normalize_page_script


CHECKPOINT_SCHEMA_VERSION = 2
CHECKPOINT_FILE_NAME = "page_export_checkpoint.json"


@dataclass
class ExportPageCheckpoint:
    page_no: int
    page_script: str
    asset_adjustments: dict[str, Any]
    page_result: dict[str, Any]


def build_export_page_signature(
    *,
    page: dict[str, Any],
    page_no: int,
    reference_image: Path,
    visual_image: Path,
    image_width: int,
    image_height: int,
    slide_width_inch: float,
    refine_rounds: int,
    asset_options: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "page_no": int(page_no),
        "reference_image": _build_file_signature(reference_image),
        "visual_image": _build_file_signature(visual_image),
        "canvas": {
            "width": int(image_width),
            "height": int(image_height),
        },
        "slide_width_inch": round(float(slide_width_inch), 6),
        "refine_rounds": int(refine_rounds),
        "asset_options": _normalize_asset_options(asset_options),
        "page_payload_hash": _stable_hash(
            {
                "texts": page.get("texts", []),
                "layout_family": str(page.get("layout_family", "")),
            }
        ),
    }


def load_export_page_checkpoint(
    page_dir: Path,
    *,
    expected_signature: dict[str, Any],
) -> ExportPageCheckpoint | None:
    checkpoint_path = page_dir / CHECKPOINT_FILE_NAME
    if not checkpoint_path.exists():
        return None

    try:
        payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None
    if int(payload.get("schema_version", 0)) != CHECKPOINT_SCHEMA_VERSION:
        return None
    if payload.get("signature") != expected_signature:
        return None

    page_no = _coerce_positive_int(payload.get("page_no"))
    if page_no is None:
        return None

    raw_script = str(payload.get("page_script", "")).strip()
    if not raw_script:
        return None
    try:
        page_script = normalize_page_script(raw_script)
    except RuntimeError:
        return None

    asset_adjustments = normalize_asset_adjustments(payload.get("asset_adjustments"))
    page_result = _normalize_page_result(payload.get("page_result"), page_no=page_no)
    return ExportPageCheckpoint(
        page_no=page_no,
        page_script=page_script,
        asset_adjustments=asset_adjustments,
        page_result=page_result,
    )


def save_export_page_checkpoint(
    page_dir: Path,
    *,
    signature: dict[str, Any],
    page_no: int,
    page_script: str,
    asset_adjustments: dict[str, Any],
    page_result: dict[str, Any],
) -> Path:
    checkpoint_path = page_dir / CHECKPOINT_FILE_NAME
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_script = normalize_page_script(str(page_script))
    normalized_adjustments = normalize_asset_adjustments(asset_adjustments)
    normalized_result = _normalize_page_result(page_result, page_no=int(page_no))
    payload = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "page_no": int(page_no),
        "signature": signature,
        "page_script": normalized_script,
        "asset_adjustments": normalized_adjustments,
        "page_result": normalized_result,
    }
    checkpoint_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return checkpoint_path


def _build_file_signature(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    stat = resolved.stat()
    return {
        "path": str(resolved),
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }


def _normalize_asset_options(asset_options: dict[str, Any]) -> dict[str, Any]:
    return {
        "alpha_threshold": int(asset_options.get("alpha_threshold", 0)),
        "min_area": int(asset_options.get("min_area", 0)),
        "min_width": int(asset_options.get("min_width", 0)),
        "min_height": int(asset_options.get("min_height", 0)),
        "padding": int(asset_options.get("padding", 0)),
        "merge_distance": int(asset_options.get("merge_distance", 0)),
        "skip_enhance": bool(asset_options.get("skip_enhance", False)),
        "skip_transparent": bool(asset_options.get("skip_transparent", False)),
        "global_alignment_version": int(asset_options.get("global_alignment_version", 0)),
    }


def _stable_hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _normalize_page_result(raw_page_result: Any, *, page_no: int) -> dict[str, Any]:
    page_result = dict(raw_page_result) if isinstance(raw_page_result, dict) else {}
    page_result["page_no"] = int(page_no)
    page_result["office_render_available"] = bool(page_result.get("office_render_available", False))
    page_result["refine_rounds_applied"] = max(0, int(page_result.get("refine_rounds_applied", 0) or 0))
    page_result["office_preview_paths"] = _normalize_existing_paths(page_result.get("office_preview_paths"))
    page_result["comparison_paths"] = _normalize_existing_paths(page_result.get("comparison_paths"))
    if isinstance(page_result.get("text_asset_overlap"), dict):
        page_result["text_asset_overlap"] = dict(page_result["text_asset_overlap"])
    if isinstance(page_result.get("asset_alignment_decision"), dict):
        page_result["asset_alignment_decision"] = dict(page_result["asset_alignment_decision"])
    return page_result


def _normalize_existing_paths(raw_paths: Any) -> list[str]:
    if not isinstance(raw_paths, list):
        return []
    result: list[str] = []
    for item in raw_paths:
        value = str(item or "").strip()
        if not value:
            continue
        path = Path(value)
        if path.exists():
            result.append(str(path))
    return result


def _coerce_positive_int(value: Any) -> int | None:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return None
    if resolved <= 0:
        return None
    return resolved
