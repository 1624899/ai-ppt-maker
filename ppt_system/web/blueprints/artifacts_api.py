from __future__ import annotations

from flask import Blueprint

from ppt_system.web.services import jobs_api_service

bp = Blueprint("artifacts_api", __name__)


@bp.get("/runs/<job_id>/<path:filename>")
def serve_run_file(job_id: str, filename: str):
    return jobs_api_service.serve_run_file(job_id, filename)
