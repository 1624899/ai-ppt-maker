from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import jsonify, request

from ppt_system.web.runtime import get_runtime_module


def api_job_db_stats():
    runtime = get_runtime_module()
    stats = runtime.collect_job_db_stats(runtime.JOBS_DB_PATH)
    return jsonify(stats)


def api_job_db_maintenance():
    runtime = get_runtime_module()
    payload = request.get_json(silent=True) or {}
    try:
        keep_latest = _parse_keep_latest(payload.get("keep_latest", 20))
        include_pinned = bool(payload.get("include_pinned", False))
        dry_run = bool(payload.get("dry_run", True))
        vacuum = bool(payload.get("vacuum", False))
        result = execute_job_db_maintenance(
            runtime.JOBS_DB_PATH,
            keep_latest=keep_latest,
            include_pinned=include_pinned,
            dry_run=dry_run,
            vacuum=vacuum,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


def execute_job_db_maintenance(
    db_path: Path,
    *,
    keep_latest: int,
    include_pinned: bool,
    dry_run: bool,
    vacuum: bool,
) -> dict[str, Any]:
    runtime = get_runtime_module()
    candidates = runtime.list_job_db_cleanup_candidates(
        db_path,
        keep_latest=keep_latest,
        include_pinned=include_pinned,
    )
    before_stats = runtime.collect_job_db_stats(db_path)
    cleaned_job_ids: list[str] = []
    removed_artifact_dirs: list[str] = []

    if not dry_run:
        for candidate in candidates:
            job_id = str(candidate.get("job_id") or "").strip()
            if not job_id:
                continue
            if runtime.is_job_managed(job_id):
                continue
            job_dir_value = str(candidate.get("job_dir") or "").strip()
            if job_dir_value:
                runtime.remove_job_artifacts(Path(job_dir_value))
                removed_artifact_dirs.append(job_dir_value)
            with runtime.JOB_STATUS_LOCK:
                runtime.JOB_STATUS_CACHE.pop(job_id, None)
            cleaned_job_ids.append(job_id)
        deleted_count = runtime.delete_job_db_records(db_path, cleaned_job_ids)
        if vacuum and (deleted_count > 0 or before_stats.get("reclaimable_bytes", 0) > 0):
            runtime.vacuum_job_db(db_path)
    after_stats = runtime.collect_job_db_stats(db_path)

    return {
        "dry_run": dry_run,
        "keep_latest": keep_latest,
        "include_pinned": include_pinned,
        "vacuum": vacuum,
        "before": before_stats,
        "after": after_stats,
        "candidate_count": len(candidates),
        "deleted_count": 0 if dry_run else len(cleaned_job_ids),
        "deleted_job_ids": [] if dry_run else cleaned_job_ids,
        "removed_artifact_dirs": [] if dry_run else removed_artifact_dirs,
        "candidates": [_serialize_candidate(item) for item in candidates],
    }


def _parse_keep_latest(value: Any) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("keep_latest 必须是非负整数。") from exc
    if normalized < 0:
        raise ValueError("keep_latest 必须是非负整数。")
    return normalized


def _serialize_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": str(candidate.get("job_id") or ""),
        "status": str(candidate.get("status") or ""),
        "title": str(candidate.get("title") or ""),
        "job_dir": str(candidate.get("job_dir") or ""),
        "pinned_at": str(candidate.get("pinned_at") or ""),
        "created_at": str(candidate.get("created_at") or ""),
        "updated_at": str(candidate.get("updated_at") or ""),
    }
