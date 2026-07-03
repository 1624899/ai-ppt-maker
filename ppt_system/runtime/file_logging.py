from __future__ import annotations

import atexit
import logging
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import TextIO


_INSTALL_LOCK = threading.Lock()
_INSTALLED_LOG_PATH: Path | None = None
_LOG_FILE: TextIO | None = None


class TeeTextStream:
    """把控制台输出同时写入日志文件，保留原始流行为。"""

    def __init__(self, stream: TextIO, log_file: TextIO) -> None:
        self._stream = stream
        self._log_file = log_file
        self._lock = threading.RLock()

    def write(self, text: str) -> int:
        with self._lock:
            written = self._stream.write(text)
            _write_log_safely(self._log_file, text)
            _flush_log_safely(self._log_file)
            return written

    def flush(self) -> None:
        with self._lock:
            self._stream.flush()
            _flush_log_safely(self._log_file)

    def isatty(self) -> bool:
        return bool(getattr(self._stream, "isatty", lambda: False)())

    def fileno(self) -> int:
        return int(getattr(self._stream, "fileno")())

    def reconfigure(self, *args: object, **kwargs: object) -> None:
        reconfigure = getattr(self._stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(*args, **kwargs)

    @property
    def encoding(self) -> str | None:
        return getattr(self._stream, "encoding", None)

    @property
    def errors(self) -> str | None:
        return getattr(self._stream, "errors", None)

    def __getattr__(self, name: str) -> object:
        return getattr(self._stream, name)


def initialize_file_logging(logs_dir: Path, *, app_name: str = "AI PPT Maker") -> Path:
    """初始化应用文件日志，返回当前进程日志文件路径。"""
    global _INSTALLED_LOG_PATH, _LOG_FILE

    resolved_logs_dir = Path(logs_dir).resolve()
    with _INSTALL_LOCK:
        if _INSTALLED_LOG_PATH is not None:
            return _INSTALLED_LOG_PATH

        resolved_logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = resolved_logs_dir / _build_log_filename()
        log_file = log_path.open("a", encoding="utf-8", buffering=1)
        _LOG_FILE = log_file
        _INSTALLED_LOG_PATH = log_path

        sys.stdout = TeeTextStream(sys.stdout, log_file)  # type: ignore[assignment]
        sys.stderr = TeeTextStream(sys.stderr, log_file)  # type: ignore[assignment]
        _configure_python_logging(log_file)
        _write_startup_banner(log_file, app_name, log_path)
        atexit.register(_close_log_file)
        return log_path


def _build_log_filename(now: datetime | None = None) -> str:
    current = now or datetime.now()
    return f"app-{current.strftime('%Y%m%d')}.log"


def _configure_python_logging(log_file: TextIO) -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    if not any(getattr(handler, "_ai_ppt_file_logging", False) for handler in root_logger.handlers):
        handler = logging.StreamHandler(log_file)
        handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"))
        setattr(handler, "_ai_ppt_file_logging", True)
        root_logger.addHandler(handler)


def _write_startup_banner(log_file: TextIO, app_name: str, log_path: Path) -> None:
    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file.write(f"[{started_at}] [runtime] {app_name} 日志启动：{log_path}\n")
    log_file.flush()


def _close_log_file() -> None:
    log_file = _LOG_FILE
    if log_file is None or log_file.closed:
        return
    _flush_log_safely(log_file)


def _write_log_safely(log_file: TextIO, text: str) -> None:
    try:
        if not log_file.closed:
            log_file.write(text)
    except (OSError, ValueError):
        return


def _flush_log_safely(log_file: TextIO) -> None:
    try:
        if not log_file.closed:
            log_file.flush()
    except (OSError, ValueError):
        return
