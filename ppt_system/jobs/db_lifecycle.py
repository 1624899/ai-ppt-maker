from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def ensure_db_parent(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)


def collect_db_stats(db_path: Path) -> dict[str, Any]:
    normalized = Path(db_path)
    exists = normalized.exists()
    stats: dict[str, Any] = {
        "path": str(normalized),
        "exists": exists,
        "size_bytes": normalized.stat().st_size if exists else 0,
        "job_count": 0,
        "pinned_job_count": 0,
        "running_job_count": 0,
        "page_count": 0,
        "freelist_count": 0,
        "page_size": 0,
        "reclaimable_bytes": 0,
    }
    if not exists:
        return stats
    with sqlite3.connect(normalized) as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS job_count,
                SUM(CASE WHEN TRIM(COALESCE(pinned_at, '')) != '' THEN 1 ELSE 0 END) AS pinned_job_count,
                SUM(CASE WHEN status IN ('queued', 'running', 'stopping') THEN 1 ELSE 0 END) AS running_job_count
            FROM jobs
            """
        ).fetchone()
        page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
        freelist_count = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
        page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
    stats["job_count"] = int(row[0] or 0)
    stats["pinned_job_count"] = int(row[1] or 0)
    stats["running_job_count"] = int(row[2] or 0)
    stats["page_count"] = page_count
    stats["freelist_count"] = freelist_count
    stats["page_size"] = page_size
    stats["reclaimable_bytes"] = freelist_count * page_size
    return stats


def list_cleanup_candidates(
    db_path: Path,
    *,
    keep_latest: int = 20,
    include_pinned: bool = False,
) -> list[dict[str, Any]]:
    normalized_keep_latest = max(0, int(keep_latest))
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT job_id, status, title, job_dir, pinned_at, created_at, updated_at
            FROM jobs
            ORDER BY updated_at DESC, rowid DESC
            """
        ).fetchall()
    candidates: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        item = dict(row)
        pinned_at = str(item.get("pinned_at") or "").strip()
        if index < normalized_keep_latest:
            continue
        if not include_pinned and pinned_at:
            continue
        if str(item.get("status") or "").strip() in {"queued", "running", "stopping"}:
            continue
        candidates.append(item)
    return candidates


def delete_jobs_by_ids(db_path: Path, job_ids: list[str]) -> int:
    normalized_job_ids = [str(job_id).strip() for job_id in job_ids if str(job_id).strip()]
    if not normalized_job_ids:
        return 0
    placeholders = ",".join("?" for _ in normalized_job_ids)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(f"DELETE FROM jobs WHERE job_id IN ({placeholders})", normalized_job_ids)
        return int(cursor.rowcount or 0)


def vacuum_db(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("VACUUM")
