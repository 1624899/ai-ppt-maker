from __future__ import annotations

from typing import Any

from flask import jsonify


def api_success(payload: Any, status: int = 200):
    return jsonify(payload), status


def api_error(message: Any, status: int = 400, **extra: Any):
    payload = {"error": str(message)}
    payload.update(extra)
    return jsonify(payload), status


def api_ok(**extra: Any):
    payload = {"ok": True}
    payload.update(extra)
    return jsonify(payload)
