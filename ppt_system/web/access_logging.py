from __future__ import annotations

import logging
import time
from typing import Any

from flask import Flask, g, request


ACCESS_LOG_MODE_KEY = "AI_PPT_HTTP_ACCESS_LOG_MODE"
ACCESS_LOG_CONFIGURED_KEY = "AI_PPT_HTTP_ACCESS_LOGGING_CONFIGURED"
DEFAULT_ACCESS_LOG_MODE = "failures"
FAILED_STATUS_CODE = 400
MAX_TARGET_LENGTH = 240

_LOGGER = logging.getLogger("ppt_system.web.access")


def configure_http_access_logging(app: Flask, mode: str | None = None) -> None:
    """配置 HTTP 访问日志，默认只记录失败请求，避免前端轮询刷屏。"""
    if app.config.get(ACCESS_LOG_CONFIGURED_KEY):
        return

    resolved_mode = normalize_access_log_mode(mode)
    app.config[ACCESS_LOG_MODE_KEY] = resolved_mode
    app.config[ACCESS_LOG_CONFIGURED_KEY] = True
    _configure_werkzeug_access_logger(resolved_mode)

    @app.before_request
    def remember_request_start_time() -> None:
        g.ai_ppt_request_started_at = time.perf_counter()

    @app.after_request
    def log_compact_http_access(response):
        if should_log_request(resolved_mode, int(response.status_code)):
            _LOGGER.log(
                _status_log_level(int(response.status_code)),
                "%s %s -> %s %.1fms",
                request.method,
                _request_target(),
                response.status_code,
                _request_elapsed_ms(),
            )
        return response


def normalize_access_log_mode(mode: str | None) -> str:
    normalized = str(mode or "").strip().lower()
    aliases = {
        "": DEFAULT_ACCESS_LOG_MODE,
        "error": "failures",
        "errors": "failures",
        "failure": "failures",
        "failed": "failures",
        "compact": "summary",
        "simple": "summary",
        "all": "full",
        "verbose": "full",
        "none": "off",
        "false": "off",
        "0": "off",
    }
    resolved = aliases.get(normalized, normalized)
    return resolved if resolved in {"failures", "summary", "full", "off"} else DEFAULT_ACCESS_LOG_MODE


def should_log_request(mode: str, status_code: int) -> bool:
    if mode == "summary":
        return True
    if mode == "failures":
        return int(status_code) >= FAILED_STATUS_CODE
    return False


def _configure_werkzeug_access_logger(mode: str) -> None:
    werkzeug_logger = logging.getLogger("werkzeug")
    if mode == "full":
        werkzeug_logger.setLevel(logging.INFO)
    else:
        werkzeug_logger.setLevel(logging.WARNING)


def _status_log_level(status_code: int) -> int:
    if int(status_code) >= 500:
        return logging.ERROR
    if int(status_code) >= 400:
        return logging.WARNING
    return logging.INFO


def _request_elapsed_ms() -> float:
    started_at = getattr(g, "ai_ppt_request_started_at", None)
    if not isinstance(started_at, (int, float)):
        return 0.0
    return max(0.0, (time.perf_counter() - float(started_at)) * 1000)


def _request_target() -> str:
    query = request.query_string.decode("utf-8", errors="replace").strip()
    target = request.path if not query else f"{request.path}?{query}"
    return _truncate_text(target, MAX_TARGET_LENGTH)


def _truncate_text(value: Any, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)]}..."
