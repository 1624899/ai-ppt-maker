from __future__ import annotations

import logging

from flask import Flask, abort

from ppt_system.web.access_logging import configure_http_access_logging, normalize_access_log_mode


def test_default_access_logging_records_failures_only(caplog) -> None:
    app = _build_test_app()
    old_werkzeug_level = logging.getLogger("werkzeug").level
    try:
        configure_http_access_logging(app)
        client = app.test_client()

        caplog.set_level(logging.INFO, logger="ppt_system.web.access")
        client.get("/ok")
        client.get("/missing")

        log_text = "\n".join(record.getMessage() for record in caplog.records)
        assert "GET /missing -> 404" in log_text
        assert "GET /ok -> 200" not in log_text
        assert logging.getLogger("werkzeug").level == logging.WARNING
    finally:
        logging.getLogger("werkzeug").setLevel(old_werkzeug_level)


def test_summary_access_logging_uses_compact_line_for_successes(caplog) -> None:
    app = _build_test_app()
    old_werkzeug_level = logging.getLogger("werkzeug").level
    try:
        configure_http_access_logging(app, "summary")
        client = app.test_client()

        caplog.set_level(logging.INFO, logger="ppt_system.web.access")
        client.get("/ok?refresh=1")

        log_text = "\n".join(record.getMessage() for record in caplog.records)
        assert "GET /ok?refresh=1 -> 200" in log_text
        assert logging.getLogger("werkzeug").level == logging.WARNING
    finally:
        logging.getLogger("werkzeug").setLevel(old_werkzeug_level)


def test_full_access_logging_keeps_werkzeug_full_mode_without_compact_duplicates(caplog) -> None:
    app = _build_test_app()
    old_werkzeug_level = logging.getLogger("werkzeug").level
    try:
        configure_http_access_logging(app, "full")
        client = app.test_client()

        caplog.set_level(logging.INFO, logger="ppt_system.web.access")
        client.get("/missing")

        assert not [record for record in caplog.records if record.name == "ppt_system.web.access"]
        assert logging.getLogger("werkzeug").level == logging.INFO
    finally:
        logging.getLogger("werkzeug").setLevel(old_werkzeug_level)


def test_access_log_mode_aliases_are_normalized() -> None:
    assert normalize_access_log_mode(None) == "failures"
    assert normalize_access_log_mode("errors") == "failures"
    assert normalize_access_log_mode("compact") == "summary"
    assert normalize_access_log_mode("all") == "full"
    assert normalize_access_log_mode("0") == "off"
    assert normalize_access_log_mode("unknown") == "failures"


def _build_test_app() -> Flask:
    app = Flask(__name__)

    @app.get("/ok")
    def ok():
        return "ok"

    @app.get("/missing")
    def missing():
        abort(404)

    return app
