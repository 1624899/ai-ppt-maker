from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ppt_system.model_config import read_config


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_CACHE_ROOT = PROJECT_ROOT / "output" / "model_cache"


def configure_model_cache_environment(
    *,
    project_root: Path | None = None,
    config: dict[str, Any] | None = None,
) -> Path:
    root = project_root or PROJECT_ROOT
    cache_root = resolve_model_cache_root(root, config)
    u2net_home = cache_root / "u2net"
    u2net_home.mkdir(parents=True, exist_ok=True)
    os.environ["U2NET_HOME"] = str(u2net_home)
    return u2net_home


def resolve_model_cache_root(
    project_root: Path,
    config: dict[str, Any] | None = None,
) -> Path:
    env_value = str(os.environ.get("U2NET_HOME", "")).strip()
    if env_value:
        return Path(env_value).expanduser().resolve().parent

    loaded_config = config if config is not None else _try_read_config(project_root)
    configured_root = str((loaded_config or {}).get("model_cache_root", "")).strip()
    if configured_root:
        candidate = Path(configured_root).expanduser()
        if not candidate.is_absolute():
            candidate = project_root / candidate
        return candidate.resolve()

    return (project_root / DEFAULT_MODEL_CACHE_ROOT.relative_to(PROJECT_ROOT)).resolve()


def _try_read_config(project_root: Path) -> dict[str, Any] | None:
    config_path = project_root / "config.json"
    if not config_path.exists():
        return None
    return read_config(config_path)
