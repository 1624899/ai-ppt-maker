from __future__ import annotations

import hashlib
from pathlib import Path


STATIC_ASSET_PATTERNS = ("*.css", "*.js")


def build_static_asset_version(root: Path) -> str:
    candidates = _collect_static_assets(root)
    if not candidates:
        return "dev"
    digest = hashlib.sha1()
    for path in candidates:
        stat = path.stat()
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
        digest.update(str(stat.st_size).encode("ascii"))
    return digest.hexdigest()[:12]


def _collect_static_assets(root: Path) -> list[Path]:
    search_roots = [
        root / "web_ui" / "dist",
        root / "front" / "static",
    ]
    assets: list[Path] = []
    for search_root in search_roots:
        if not search_root.exists():
            continue
        for pattern in STATIC_ASSET_PATTERNS:
            assets.extend(path for path in search_root.rglob(pattern) if path.is_file())
    return sorted(assets, key=lambda item: str(item.relative_to(root)))
