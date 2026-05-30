from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit


def normalize_api_base_url(raw_url: str) -> str:
    value = str(raw_url or "").strip()
    if not value:
        return ""

    parts = urlsplit(value)
    if parts.scheme and parts.netloc:
        normalized_path = re.sub(r"/{2,}", "/", parts.path or "")
        normalized_parts = (
            parts.scheme,
            parts.netloc,
            normalized_path.rstrip("/"),
            parts.query,
            parts.fragment,
        )
        return urlunsplit(normalized_parts)

    collapsed = re.sub(r"/{2,}", "/", value)
    return collapsed.rstrip("/")
