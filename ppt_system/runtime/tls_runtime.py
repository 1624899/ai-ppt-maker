from __future__ import annotations

import os
from pathlib import Path


def configure_ca_bundle() -> str:
    """统一配置 requests 使用的 CA 文件，兼容源码与 PyInstaller 环境。"""
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
