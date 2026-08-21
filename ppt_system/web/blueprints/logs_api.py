from __future__ import annotations

from flask import Blueprint, jsonify, request

from ppt_system.web.services import logs_api_service

bp = Blueprint("logs_api", __name__)


@bp.get("/api/logs")
def api_list_logs():
    return jsonify({"files": logs_api_service.list_log_files()})


@bp.get("/api/logs/<path:name>")
def api_read_log(name: str):
    try:
        lines = int(request.args.get("lines", logs_api_service.DEFAULT_TAIL_LINES))
    except ValueError:
        lines = logs_api_service.DEFAULT_TAIL_LINES
    try:
        return jsonify(logs_api_service.read_log_tail(name, lines))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
