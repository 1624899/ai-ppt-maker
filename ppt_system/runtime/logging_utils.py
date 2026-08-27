from __future__ import annotations

from datetime import datetime


def format_log_line(scope: str, message: str) -> str:
    timestamp = datetime.now().strftime("%H:%M:%S")
    return f"[{timestamp}] [{scope}] {message}"


def format_stage_tag(stage: str) -> str:
    """把业务阶段格式化成统一的日志标签，例如“（阶段：内容规划）”。"""
    text = str(stage or "").strip()
    return f"（阶段：{text}）" if text else ""
