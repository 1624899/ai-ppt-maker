from __future__ import annotations

from flask import Blueprint

from ppt_system.web.services import jobs_api_service

bp = Blueprint("jobs_api", __name__)


@bp.post("/api/jobs")
def api_create_job():
    return jobs_api_service.api_create_job()


@bp.get("/api/jobs/<job_id>")
def api_job_status(job_id: str):
    return jobs_api_service.api_job_status(job_id)


@bp.get("/api/jobs/<job_id>/stream")
def api_job_stream(job_id: str):
    return jobs_api_service.api_job_stream(job_id)


@bp.get("/api/jobs")
def api_job_history():
    return jobs_api_service.api_job_history()


@bp.delete("/api/jobs/<job_id>")
def api_delete_job(job_id: str):
    return jobs_api_service.api_delete_job(job_id)


@bp.get("/api/jobs/stream")
def api_job_history_stream():
    return jobs_api_service.api_job_history_stream()


@bp.post("/api/jobs/<job_id>/interrupt")
def api_interrupt_job(job_id: str):
    return jobs_api_service.api_interrupt_job(job_id)


@bp.post("/api/jobs/<job_id>/resume")
def api_resume_job(job_id: str):
    return jobs_api_service.api_resume_job(job_id)


@bp.post("/api/jobs/<job_id>/deliver")
def api_deliver_job(job_id: str):
    return jobs_api_service.api_deliver_job(job_id)
