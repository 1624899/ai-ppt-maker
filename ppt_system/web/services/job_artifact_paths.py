from __future__ import annotations

from pathlib import Path
from typing import Any


SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def resolve_job_artifact_path(job_dir: Path, job_id: str, value: Any) -> Path | None:
    """把任务状态中的图片引用解析为真实文件路径。"""
    raw_value = normalize_artifact_ref(value)
    if not raw_value:
        return None

    run_prefix = f"/runs/{job_id}/"
    if raw_value.startswith(run_prefix):
        path = job_dir / raw_value[len(run_prefix):]
    elif raw_value.startswith(f"runs/{job_id}/"):
        path = job_dir / raw_value[len(f"runs/{job_id}/"):]
    elif raw_value.startswith("/runs/") or raw_value.startswith("runs/"):
        return None
    else:
        candidate = Path(raw_value)
        path = candidate if candidate.is_absolute() else job_dir / raw_value.lstrip("/\\")

    if path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        return None
    if not _is_within_directory(path, job_dir):
        return None
    return path if path.exists() and path.is_file() else None


def normalize_artifact_ref(value: Any) -> str:
    return str(value or "").strip()


def _is_within_directory(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
    except (OSError, ValueError):
        return False
    return True
