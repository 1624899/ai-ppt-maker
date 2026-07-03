from __future__ import annotations

import io
import logging
import sys

from ppt_system.runtime import file_logging
from ppt_system.runtime.file_logging import initialize_file_logging


def test_initialize_file_logging_writes_stdout_and_stderr_to_utf8_log(tmp_path, monkeypatch) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    _reset_file_logging_state(monkeypatch)

    log_path = initialize_file_logging(tmp_path / "logs", app_name="测试应用")

    print("标准输出：你好", flush=True)
    print("错误输出：再见", file=sys.stderr, flush=True)
    sys.stdout.flush()
    sys.stderr.flush()

    content = log_path.read_text(encoding="utf-8")
    assert log_path.parent == tmp_path / "logs"
    assert "测试应用 日志启动" in content
    assert "标准输出：你好" in content
    assert "错误输出：再见" in content
    assert stdout.getvalue() == "标准输出：你好\n"
    assert stderr.getvalue() == "错误输出：再见\n"


def test_initialize_file_logging_is_idempotent(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    _reset_file_logging_state(monkeypatch)

    first_path = initialize_file_logging(tmp_path / "logs")
    second_path = initialize_file_logging(tmp_path / "other-logs")

    assert second_path == first_path
    assert not (tmp_path / "other-logs").exists()


def test_initialize_file_logging_attaches_python_logging_handler(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    _reset_file_logging_state(monkeypatch)

    log_path = initialize_file_logging(tmp_path / "logs")
    logging.getLogger("ai_ppt_test").warning("结构化日志：保留")

    content = log_path.read_text(encoding="utf-8")
    assert "[WARNING] [ai_ppt_test] 结构化日志：保留" in content


def _reset_file_logging_state(monkeypatch) -> None:
    log_file = file_logging._LOG_FILE
    if log_file is not None and not log_file.closed:
        log_file.close()
    monkeypatch.setattr(file_logging, "_INSTALLED_LOG_PATH", None)
    monkeypatch.setattr(file_logging, "_LOG_FILE", None)
    root_logger = logging.getLogger()
    root_logger.handlers = [
        handler for handler in root_logger.handlers if not getattr(handler, "_ai_ppt_file_logging", False)
    ]
