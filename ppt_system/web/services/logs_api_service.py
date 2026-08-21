from __future__ import annotations

import re
from pathlib import Path

from ppt_system.runtime import runtime_context

# 只允许读取日志目录下按日期命名的应用日志文件，防止路径穿越。
_LOG_FILENAME_PATTERN = re.compile(r"^app-\d{8}\.log$")
DEFAULT_TAIL_LINES = 200
MAX_TAIL_LINES = 1000


def _logs_dir() -> Path:
    return Path(runtime_context.LOGS_DIR).resolve()


def list_log_files() -> list[dict[str, object]]:
    """列出日志目录下的应用日志文件，按文件名倒序（最新的在前）。"""
    logs_dir = _logs_dir()
    if not logs_dir.exists():
        return []
    result: list[dict[str, object]] = []
    for path in logs_dir.iterdir():
        if not path.is_file() or not _LOG_FILENAME_PATTERN.match(path.name):
            continue
        stat = path.stat()
        result.append({"name": path.name, "size": stat.st_size, "modified_at": stat.st_mtime})
    return sorted(result, key=lambda item: str(item["name"]), reverse=True)


def read_log_tail(name: str, lines: int = DEFAULT_TAIL_LINES) -> dict[str, object]:
    """读取指定日志文件的末尾若干行，返回文本行列表。"""
    if not _LOG_FILENAME_PATTERN.match(name):
        raise ValueError(f"非法的日志文件名：{name}")
    requested = max(1, min(int(lines), MAX_TAIL_LINES))
    path = _logs_dir() / name
    if not path.is_file():
        raise FileNotFoundError(f"日志文件不存在：{name}")
    with path.open("r", encoding="utf-8", errors="replace") as log_file:
        tail = log_file.readlines()[-requested:]
    return {"name": name, "lines": [line.rstrip("\n") for line in tail]}
