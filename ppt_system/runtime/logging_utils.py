from __future__ import annotations

from datetime import datetime


def format_log_line(scope: str, message: str) -> str:
    timestamp = datetime.now().strftime("%H:%M:%S")
    return f"[{timestamp}] [{scope}] {message}"
