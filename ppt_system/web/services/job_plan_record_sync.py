from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ppt_system.jobs.job_store import get_job, update_job


def resolve_current_style_notes(state: Mapping[str, Any], record: Mapping[str, Any] | None = None) -> str:
    """读取当前规划采用的风格补充。"""
    plan = state.get("plan", {}) if isinstance(state.get("plan"), Mapping) else {}
    job_meta = state.get("job_meta", {}) if isinstance(state.get("job_meta"), Mapping) else {}
    for value in (
        plan.get("style_notes"),
        job_meta.get("style_notes"),
        (record or {}).get("style_notes"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    return ""


def sync_plan_metadata_to_job_record(db_path: Path, job_id: str, state: Mapping[str, Any]) -> dict[str, Any] | None:
    """把当前规划的可恢复参数同步到任务主记录。"""
    record = get_job(db_path, job_id)
    if not record:
        return None

    job_meta = state.get("job_meta", {}) if isinstance(state.get("job_meta"), Mapping) else {}
    pages = state.get("pages", []) if isinstance(state.get("pages"), list) else []
    page_count = int(job_meta.get("page_count") or len(pages) or record.get("page_count") or 0)
    style_notes = resolve_current_style_notes(state, record)
    request_payload = dict(record.get("request", {}) if isinstance(record.get("request"), dict) else {})
    request_payload["style_notes"] = style_notes
    request_payload["page_count"] = page_count

    update_job(
        db_path,
        job_id,
        style_notes=style_notes,
        page_count=page_count,
        request=request_payload,
    )
    return get_job(db_path, job_id)
