from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ppt_system.export.export_step_checkpoint import build_file_content_signature, stable_hash_payload


ASSET_CHECKPOINT_SCHEMA_VERSION = 1
ASSET_CHECKPOINT_FILE_NAME = "asset_prepare_checkpoint.json"


@dataclass(frozen=True)
class ExportAssetPrepareCheckpoint:
    signature: dict[str, Any]
    payload: dict[str, Any]
    path: Path


def build_export_asset_prepare_signature(
    *,
    page_no: int,
    reference_image: Path,
    visual_image: Path,
    image_width: int,
    image_height: int,
    slide_width_inch: float,
    text_placeholders: dict[str, Any],
    asset_options: dict[str, Any],
) -> dict[str, Any]:
    """构建资产准备签名，确保输入图片、占位框或切分参数变化时不会误用旧资产。"""
    return {
        "schema_version": ASSET_CHECKPOINT_SCHEMA_VERSION,
        "operation": "direct_page_asset_prepare",
        "page_no": int(page_no),
        "reference_image": build_file_content_signature(reference_image),
        "visual_image": build_file_content_signature(visual_image),
        "canvas": {
            "width": int(image_width),
            "height": int(image_height),
        },
        "slide_width_inch": round(float(slide_width_inch), 6),
        "text_placeholders_hash": stable_hash_payload(text_placeholders),
        "asset_options_hash": stable_hash_payload(asset_options),
    }


def load_export_asset_prepare_checkpoint(
    page_dir: Path,
    *,
    expected_signature: dict[str, Any],
) -> ExportAssetPrepareCheckpoint | None:
    checkpoint_path = page_dir / ASSET_CHECKPOINT_FILE_NAME
    if not checkpoint_path.exists():
        return None

    try:
        body = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(body, dict):
        return None
    if int(body.get("schema_version", 0)) != ASSET_CHECKPOINT_SCHEMA_VERSION:
        return None
    signature = body.get("signature")
    if signature != expected_signature:
        return None
    payload = body.get("payload")
    if not isinstance(payload, dict):
        return None
    return ExportAssetPrepareCheckpoint(
        signature=dict(signature),
        payload=dict(payload),
        path=checkpoint_path,
    )


def save_export_asset_prepare_checkpoint(
    page_dir: Path,
    *,
    signature: dict[str, Any],
    payload: dict[str, Any],
) -> Path:
    checkpoint_path = page_dir / ASSET_CHECKPOINT_FILE_NAME
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "schema_version": ASSET_CHECKPOINT_SCHEMA_VERSION,
        "signature": signature,
        "payload": _json_roundtrip(payload),
    }
    temp_path = checkpoint_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(checkpoint_path)
    return checkpoint_path


def _json_roundtrip(payload: Any) -> Any:
    return json.loads(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
