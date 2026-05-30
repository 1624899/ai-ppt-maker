from __future__ import annotations

from flask import Blueprint

from ppt_system.web.services import job_agent_draft_service
from ppt_system.web.services import job_image_edit_service
from ppt_system.web.services import job_operations_service
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


@bp.patch("/api/jobs/<job_id>")
def api_update_job(job_id: str):
    return jobs_api_service.api_update_job(job_id)


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


@bp.post("/api/jobs/<job_id>/operations")
def api_create_job_operation(job_id: str):
    return job_operations_service.api_create_job_operation(job_id)


@bp.post("/api/jobs/<job_id>/image-edit-candidates")
def api_create_image_edit_candidate(job_id: str):
    return job_image_edit_service.api_create_image_edit_candidate(job_id)


@bp.post("/api/jobs/<job_id>/image-edit-candidates/<candidate_id>/apply")
def api_apply_image_edit_candidate(job_id: str, candidate_id: str):
    return job_image_edit_service.api_apply_image_edit_candidate(job_id, candidate_id)


@bp.post("/api/jobs/<job_id>/agent/draft")
def api_create_agent_draft(job_id: str):
    return job_agent_draft_service.api_create_agent_draft(job_id)


@bp.delete("/api/jobs/<job_id>/agent/conversation")
def api_clear_agent_conversation(job_id: str):
    return job_agent_draft_service.api_clear_agent_conversation(job_id)
