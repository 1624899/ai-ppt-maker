from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ppt_system.runtime.time_utils import utc_timestamp_millis


JOB_JSON_FIELD_COLUMNS = {
    "request": "request_json",
    "state": "state_json",
    "result": "result_json",
}
JOB_UPDATE_COLUMNS = {
    "status",
    "current_stage",
    "title",
    "content",
    "page_count",
    "image_preset",
    "image_quality",
    "style_notes",
    "job_dir",
    "stop_requested",
    "pinned_at",
    "created_at",
    "updated_at",
    *JOB_JSON_FIELD_COLUMNS,
}


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                current_stage TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                page_count INTEGER NOT NULL,
                image_preset TEXT NOT NULL,
                image_quality TEXT NOT NULL,
                style_notes TEXT NOT NULL,
                job_dir TEXT NOT NULL,
                request_json TEXT NOT NULL,
                state_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                stop_requested INTEGER NOT NULL DEFAULT 0,
                pinned_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        _ensure_column(conn, "jobs", "pinned_at", "TEXT NOT NULL DEFAULT ''")


def create_job(db_path: Path, payload: dict[str, Any]) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                job_id, status, current_stage, title, content, page_count, image_preset,
                image_quality, style_notes, job_dir, request_json, state_json, result_json,
                stop_requested, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                payload["job_id"],
                payload["status"],
                payload["current_stage"],
                payload["title"],
                payload["content"],
                int(payload["page_count"]),
                payload["image_preset"],
                payload["image_quality"],
                payload["style_notes"],
                payload["job_dir"],
                json.dumps(payload["request"], ensure_ascii=False),
                json.dumps(payload.get("state", {}), ensure_ascii=False),
                json.dumps(payload.get("result", {}), ensure_ascii=False),
                1 if payload.get("stop_requested") else 0,
            ),
        )


def update_job(db_path: Path, job_id: str, touch_updated_at: bool = True, **fields: Any) -> None:
    if not fields:
        return
    columns = []
    values = []
    for key, value in fields.items():
        if key not in JOB_UPDATE_COLUMNS:
            raise ValueError(f"不支持更新任务字段：{key}")
        if key in JOB_JSON_FIELD_COLUMNS:
            columns.append(f"{JOB_JSON_FIELD_COLUMNS[key]} = ?")
            values.append(json.dumps(value or {}, ensure_ascii=False))
        elif key == "stop_requested":
            columns.append("stop_requested = ?")
            values.append(1 if value else 0)
        else:
            columns.append(f"{key} = ?")
            values.append(value)
    if touch_updated_at:
        columns.append("updated_at = ?")
        values.append(current_timestamp())
    values.append(job_id)
    with sqlite3.connect(db_path) as conn:
        conn.execute(f"UPDATE jobs SET {', '.join(columns)} WHERE job_id = ?", values)


def get_job(db_path: Path, job_id: str) -> dict[str, Any] | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    if not row:
        return None
    return _row_to_job(dict(row))


def list_jobs(db_path: Path, limit: int | None = 100) -> list[dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        if limit is None:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY updated_at DESC, rowid DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY updated_at DESC, rowid DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
    return [_row_to_job(dict(row)) for row in rows]


def delete_job(db_path: Path, job_id: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))


def _row_to_job(row: dict[str, Any]) -> dict[str, Any]:
    row["request"] = _load_json(row.pop("request_json", "{}"))
    row["state"] = _load_json(row.pop("state_json", "{}"))
    row["result"] = _load_json(row.pop("result_json", "{}"))
    row["stop_requested"] = bool(row.get("stop_requested"))
    row["pinned_at"] = str(row.get("pinned_at") or "")
    return row


def _load_json(value: str) -> dict[str, Any]:
    try:
        data = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def current_timestamp() -> str:
    return utc_timestamp_millis()


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")
