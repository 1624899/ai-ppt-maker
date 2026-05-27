from __future__ import annotations

from pathlib import Path
from typing import Any


def resolve_assets_dir_from_manifest(manifest: dict[str, Any]) -> Path:
    """优先使用清单中的显式资产目录，回退到旧版 source_image 推导。"""
    assets_dir = str(manifest.get("assets_dir", "")).strip()
    if assets_dir:
        return Path(assets_dir).resolve()
    source_image = Path(str(manifest.get("source_image", ""))).resolve()
    return source_image.parent / "assets"
