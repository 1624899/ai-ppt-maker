from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


STEP_CHECKPOINT_SCHEMA_VERSION = 1
STEP_CHECKPOINT_DIR_NAME = "step_checkpoints"


@dataclass
class ExportStepCheckpoint:
    step_name: str
    signature: dict[str, Any]
    payload: dict[str, Any]
    path: Path


def build_export_step_signature(
    *,
    step_name: str,
    operation: str,
    page_signature: dict[str, Any],
    provider: Any,
    inputs: dict[str, Any],
) -> dict[str, Any]:
    """构建页内子步骤签名，避免模型、提示词或输入变化时误用旧结果。"""
    return {
        "schema_version": STEP_CHECKPOINT_SCHEMA_VERSION,
        "step_name": _normalize_step_name(step_name),
        "operation": str(operation),
        "page_no": int(page_signature.get("page_no", 0) or 0),
        "page_signature_hash": stable_hash_payload(page_signature),
        "provider": build_provider_signature(provider),
        "inputs_hash": stable_hash_payload(inputs),
    }


def build_provider_signature(provider: Any) -> dict[str, Any]:
    """只记录会影响输出的模型参数，不写入 API Key。"""
    return {
        "provider_class": provider.__class__.__name__,
        "base_url": str(getattr(provider, "api_base_url", "")),
        "model": str(getattr(provider, "model", "")),
        "temperature": _json_scalar(getattr(provider, "temperature", None)),
        "max_tokens": _json_scalar(getattr(provider, "max_tokens", None)),
        "reasoning_effort": str(getattr(provider, "reasoning_effort", "")),
    }


def load_export_step_checkpoint(
    page_dir: Path,
    *,
    step_name: str,
    expected_signature: dict[str, Any],
) -> ExportStepCheckpoint | None:
    checkpoint_path = build_export_step_checkpoint_path(
        page_dir,
        step_name=step_name,
        signature=expected_signature,
    )
    if not checkpoint_path.exists():
        return None

    try:
        payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None
    if int(payload.get("schema_version", 0)) != STEP_CHECKPOINT_SCHEMA_VERSION:
        return None
    normalized_step_name = _normalize_step_name(step_name)
    if payload.get("step_name") != normalized_step_name:
        return None
    signature = payload.get("signature")
    if signature != expected_signature:
        return None
    result_payload = payload.get("payload")
    if not isinstance(result_payload, dict):
        return None
    return ExportStepCheckpoint(
        step_name=normalized_step_name,
        signature=dict(signature),
        payload=dict(result_payload),
        path=checkpoint_path,
    )


def save_export_step_checkpoint(
    page_dir: Path,
    *,
    step_name: str,
    signature: dict[str, Any],
    payload: dict[str, Any],
) -> Path:
    checkpoint_path = build_export_step_checkpoint_path(page_dir, step_name=step_name, signature=signature)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_step_name = _normalize_step_name(step_name)
    body = {
        "schema_version": STEP_CHECKPOINT_SCHEMA_VERSION,
        "step_name": normalized_step_name,
        "signature": signature,
        "payload": _json_roundtrip(payload),
    }
    temp_path = checkpoint_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(checkpoint_path)
    return checkpoint_path


def build_export_step_checkpoint_path(page_dir: Path, *, step_name: str, signature: dict[str, Any]) -> Path:
    normalized_step_name = _normalize_step_name(step_name)
    signature_hash = stable_hash_payload(signature)[:16]
    return page_dir / STEP_CHECKPOINT_DIR_NAME / f"{normalized_step_name}.{signature_hash}.json"


def build_file_content_signature(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    stat = resolved.stat()
    digest = hashlib.sha1()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(resolved),
        "size": int(stat.st_size),
        "sha1": digest.hexdigest(),
    }


def stable_hash_payload(payload: Any) -> str:
    normalized = json.dumps(_json_roundtrip(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def _normalize_step_name(step_name: str) -> str:
    value = str(step_name or "").strip().lower()
    if not value:
        raise ValueError("子步骤名称不能为空。")
    return re.sub(r"[^a-z0-9_.-]+", "_", value).strip("._-")


def _json_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _json_roundtrip(payload: Any) -> Any:
    return json.loads(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
