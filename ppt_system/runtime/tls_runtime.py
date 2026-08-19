from __future__ import annotations

import os
from pathlib import Path


def configure_ca_bundle() -> str:
    """未显式配置 CA 时使用 certifi，兼容源码与 PyInstaller 环境。"""
    configured = str(os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE") or "").strip()
    if configured:
        return configured
    try:
        import certifi
        candidate = Path(certifi.where())
    except (ImportError, OSError):
        return ""
    if not candidate.is_file():
        return ""
    resolved = str(candidate.resolve())
    os.environ["REQUESTS_CA_BUNDLE"] = resolved
    os.environ["SSL_CERT_FILE"] = resolved
    return resolved
