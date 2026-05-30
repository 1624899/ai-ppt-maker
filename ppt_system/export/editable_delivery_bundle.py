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
from ppt_system.export.export_layer_mode import count_output_slides
from ppt_system.export.text_script_runtime import build_project_script_source, execute_generated_text_script


def write_editable_delivery_bundle(
    bundle_path: Path,
    *,
    project: dict[str, Any],
    work_dir: Path,
    page_scripts: list[dict[str, Any]],
    assets: dict[str, Any],
    page_results: list[dict[str, Any]],
    default_output_pptx: Path,
    default_layer_mode: str,
) -> dict[str, Any]:
    payload = {
        "project": project,
        "work_dir": str(work_dir),
        "page_scripts": page_scripts,
        "assets": assets,
        "page_results": page_results,
        "default_output_pptx": str(default_output_pptx),
        "default_layer_mode": normalize_editable_delivery_layer_mode(default_layer_mode),
    }
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def load_editable_delivery_bundle(bundle_path: Path) -> dict[str, Any]:
    if not bundle_path.exists():
        raise FileNotFoundError(f"可编辑导出 bundle 不存在：{bundle_path}")
    payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"可编辑导出 bundle 格式错误：{bundle_path}")
    return payload


def build_editable_delivery_script_path(
    work_dir: Path,
    layer_mode: str,
) -> Path:
    resolved_layer_mode = normalize_editable_delivery_layer_mode(layer_mode)
    return work_dir / f"generated_text_layout.{resolved_layer_mode}.py"


def export_editable_delivery_from_bundle(
    bundle_path: Path,
    output_pptx: Path,
    *,
    layer_mode: str,
) -> dict[str, Any]:
    payload = load_editable_delivery_bundle(bundle_path)
    project = dict(payload.get("project") or {})
    work_dir = Path(str(payload.get("work_dir") or "")).resolve()
    page_scripts = list(payload.get("page_scripts") or [])
    resolved_layer_mode = normalize_editable_delivery_layer_mode(
        layer_mode,
        default=str(payload.get("default_layer_mode") or ""),
    )
    script_path = build_editable_delivery_script_path(work_dir, resolved_layer_mode)
    script_source = build_project_script_source(
        project,
        work_dir,
        output_pptx,
        page_scripts,
        include_assets=True,
        layer_mode=resolved_layer_mode,
    )
    script_path.write_text(script_source, encoding="utf-8")
    execute_generated_text_script(script_path)
    logical_page_count = len(project.get("pages", []))
    return {
        "output_pptx": str(output_pptx),
        "text_script_path": str(script_path),
        "work_dir": str(work_dir),
        "logical_page_count": logical_page_count,
        "page_count": count_output_slides(logical_page_count, resolved_layer_mode),
        "delivery_mode": build_editable_delivery_mode(resolved_layer_mode),
        "layer_mode": resolved_layer_mode,
        "label": build_editable_delivery_label(resolved_layer_mode),
        "description": build_editable_delivery_description(resolved_layer_mode),
        "assets": dict(payload.get("assets") or {}),
        "page_results": list(payload.get("page_results") or []),
    }
