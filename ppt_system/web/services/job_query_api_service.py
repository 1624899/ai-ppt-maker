from __future__ import annotations

import json
import time

from flask import Response, jsonify, stream_with_context

from ppt_system.web.services.api_response import api_error
from ppt_system.web.services.app_config_runtime import read_config
from ppt_system.web.services.job_api_common import _resolve_job_dir
from ppt_system.web.services.job_event_bus import JOB_EVENT_BUS
from ppt_system.web.services.job_state_view import get_job_state_snapshot, list_job_summaries

def api_job_status(job_id: str):
    config = read_config()
    job_dir = _resolve_job_dir(config, job_id)
    state, _record = get_job_state_snapshot(job_id, job_dir)
    if not state:
        return api_error("任务不存在", 404)
    return jsonify(state)

def api_job_stream(job_id: str):
    config = read_config()
    job_dir = _resolve_job_dir(config, job_id)
    initial_state, _record = get_job_state_snapshot(job_id, job_dir)
    if not initial_state:
        return api_error("任务不存在", 404)

    @stream_with_context
    def event_stream():
        last_payload = ""
        heartbeat_at = time.monotonic()
        last_version = JOB_EVENT_BUS.job_version(job_id)
        yield "retry: 1500\n\n"
        while True:
            state, _record = get_job_state_snapshot(job_id, job_dir)
            if not state:
                yield 'event: error\ndata: {"error":"任务不存在"}\n\n'
                break

            payload = json.dumps(state, ensure_ascii=False)
            if payload != last_payload:
                last_payload = payload
                yield f"event: job\ndata: {payload}\n\n"
                heartbeat_at = time.monotonic()

            resume_control = state.get("resume_control", {}) if isinstance(state.get("resume_control"), dict) else {}
            if state.get("status") in {"completed", "error", "interrupted"} and not resume_control.get("is_waiting_for_stop"):
                break

            now = time.monotonic()
            if now - heartbeat_at >= 15:
                yield ": keep-alive\n\n"
                heartbeat_at = now
            wait_seconds = max(0.1, min(15.0, 15.0 - (time.monotonic() - heartbeat_at)))
            last_version = JOB_EVENT_BUS.wait_for_job_change(job_id, last_version, wait_seconds)

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

def api_job_history():
    return jsonify({"items": list_job_summaries(limit=100)})

def api_job_history_stream():
    @stream_with_context
    def event_stream():
        last_payload = ""
        heartbeat_at = time.monotonic()
        last_version = JOB_EVENT_BUS.history_version()
        yield "retry: 2000\n\n"
        while True:
            payload = json.dumps({"items": list_job_summaries(limit=100)}, ensure_ascii=False)
            if payload != last_payload:
                last_payload = payload
                yield f"event: history\ndata: {payload}\n\n"
                heartbeat_at = time.monotonic()
            now = time.monotonic()
            if now - heartbeat_at >= 15:
                yield ": keep-alive\n\n"
                heartbeat_at = now
            wait_seconds = max(0.1, min(15.0, 15.0 - (time.monotonic() - heartbeat_at)))
            last_version = JOB_EVENT_BUS.wait_for_history_change(last_version, wait_seconds)

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
