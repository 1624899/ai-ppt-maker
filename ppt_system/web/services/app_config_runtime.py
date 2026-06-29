from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ppt_system.web.runtime import get_runtime_module


def _runtime():
    return get_runtime_module()


def read_config() -> dict[str, Any]:
    runtime = _runtime()
    return runtime.read_json_config(
        runtime.CONFIG_PATH,
        local_path=getattr(runtime, "LOCAL_CONFIG_PATH", None),
        env_path=getattr(runtime, "ENV_PATH", None),
    )


def resolve_image_preset(config: dict[str, Any], preset_name: str) -> dict[str, Any]:
    presets = config.get("image_presets", {})
    default_name = str(config.get("default_image_preset", "2k"))
    selected_name = preset_name or default_name
    if selected_name not in presets:
        raise ValueError(f"图像尺寸只能选择：{', '.join(presets.keys())}")

    preset = dict(presets[selected_name])
    preset["name"] = selected_name
    return preset


def build_export_options(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "alpha_threshold": int(config.get("split_alpha_threshold", 8)),
        "min_area": int(config.get("split_min_area", 8)),
        "padding": int(config.get("split_padding", 0)),
        "merge_distance": int(config.get("split_merge_distance", 6)),
        "skip_enhance": bool(config.get("skip_export_enhance", False)),
        "skip_transparent": bool(config.get("skip_export_transparent", False)),
        "script_refine_rounds": int(config.get("text_script_refine_rounds", 1)),
        "export_page_concurrency": max(1, int(config.get("export_page_concurrency", 1))),
    }


def list_style_reference_images(job_id: str, job_dir: Path) -> list[dict[str, Any]]:
    refs_dir = job_dir / "style_refs"
    if not refs_dir.exists():
        return []
    items: list[dict[str, Any]] = []
    for file in sorted(refs_dir.iterdir(), key=lambda item: item.name.lower()):
        if not file.is_file():
            continue
        items.append(
            {
                "name": file.name,
                "url": f"/runs/{job_id}/style_refs/{file.name}",
                "size": int(file.stat().st_size),
            }
        )
    return items


def copy_style_reference_images(source_job_dir: Path, target_refs_dir: Path) -> list[Path]:
    source_refs_dir = source_job_dir / "style_refs"
    if not source_refs_dir.exists():
        return []
    copied_files: list[Path] = []
    for file in sorted(source_refs_dir.iterdir(), key=lambda item: item.name.lower()):
        if not file.is_file():
            continue
        target = target_refs_dir / file.name
        shutil.copy2(file, target)
        copied_files.append(target)
    return copied_files
