from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Any


APP_NAME = "AI PPT Maker"
DATA_DIR_ENV = "PPT_SYSTEM_DATA_DIR"
DATA_MODE_ENV = "PPT_SYSTEM_DATA_MODE"


@dataclass(frozen=True)
class RuntimePaths:
    app_root: Path
    data_dir: Path
    config_path: Path
    local_config_path: Path
    env_path: Path
    default_output_dir: Path
    logs_dir: Path
    data_mode: str


def resolve_application_root(source_file: str) -> Path:
    """解析源码运行和 PyInstaller 运行时的资源根目录。"""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and frozen_root:
        return Path(str(frozen_root)).resolve()
    return Path(source_file).resolve().parent


def resolve_runtime_paths(
    app_root: Path,
    *,
    app_name: str = APP_NAME,
    frozen: bool | None = None,
    executable_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    platform_name: str | None = None,
) -> RuntimePaths:
    current_env = os.environ if env is None else env
    resolved_app_root = Path(app_root).resolve()
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    writable_base_dir = resolve_writable_base_dir(
        resolved_app_root,
        frozen=is_frozen,
        executable_path=executable_path,
    )
    mode = str(current_env.get(DATA_MODE_ENV, "")).strip().lower()

    explicit_data_dir = str(current_env.get(DATA_DIR_ENV, "")).strip()
    if explicit_data_dir:
        data_dir = Path(explicit_data_dir).expanduser()
        data_mode = "custom"
    elif mode == "project":
        data_dir = writable_base_dir
        data_mode = "project"
    elif mode == "portable":
        data_dir = writable_base_dir / "data"
        data_mode = "portable"
    elif mode in {"appdata", "user"} or is_frozen:
        data_dir = resolve_user_data_dir(app_name, env=current_env, platform_name=platform_name)
        data_mode = "appdata"
    else:
        data_dir = resolved_app_root
        data_mode = "project"

    data_dir = data_dir.resolve()
    return RuntimePaths(
        app_root=resolved_app_root,
        data_dir=data_dir,
        config_path=resolved_app_root / "config.json",
        local_config_path=data_dir / "config.local.json",
        env_path=data_dir / ".env",
        default_output_dir=data_dir / "output",
        logs_dir=data_dir / "logs",
        data_mode=data_mode,
    )


def resolve_writable_base_dir(
    app_root: Path,
    *,
    frozen: bool,
    executable_path: str | Path | None = None,
) -> Path:
    """解析可写数据的基准目录，避免 PyInstaller 单文件模式写入临时资源目录。"""
    if frozen:
        resolved_executable = Path(executable_path) if executable_path is not None else Path(sys.executable)
        return resolved_executable.resolve().parent
    return Path(app_root).resolve()


def resolve_user_data_dir(
    app_name: str = APP_NAME,
    *,
    env: Mapping[str, str] | None = None,
    platform_name: str | None = None,
) -> Path:
    current_env = os.environ if env is None else env
    resolved_platform = os.name if platform_name is None else platform_name
    if resolved_platform == "nt":
        base = str(current_env.get("APPDATA", "")).strip()
        if base:
            return Path(base) / app_name
        return Path.home() / "AppData" / "Roaming" / app_name
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / app_name
    xdg_home = str(current_env.get("XDG_DATA_HOME", "")).strip()
    if xdg_home:
        return Path(xdg_home) / app_name
    return Path.home() / ".local" / "share" / app_name


def ensure_runtime_directories(paths: RuntimePaths) -> None:
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    paths.default_output_dir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)


def resolve_configured_output_root(paths: RuntimePaths, config: Mapping[str, Any]) -> Path:
    raw_output_dir = str(config.get("output_dir", "output") or "output").strip()
    output_dir = Path(raw_output_dir)
    if output_dir.is_absolute():
        return output_dir.resolve()
    return (paths.data_dir / output_dir).resolve()


def resolve_configured_job_dir(paths: RuntimePaths, config: Mapping[str, Any], job_id: str) -> Path:
    return resolve_configured_output_root(paths, config) / str(job_id)
