from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from ppt_system.web.runtime import get_runtime_module
from ppt_system.generation.title_extraction import derive_title_from_content

RUNTIME_STATE_FIELDS = ("status", "current_stage", "stop_requested")
NON_TERMINAL_JOB_STATUSES = {"", "pending", "queued", "running", "stopping"}
NON_TERMINAL_JOB_STATUSES.add("awaiting_plan_confirmation")
STAGE_TERMINAL_STATUSES = {"error", "interrupted"}
RESUMABLE_STAGE_STATUSES = STAGE_TERMINAL_STATUSES | {"stopping"}
DEFAULT_STALE_STOPPING_GRACE_SECONDS = 300


def _runtime():
    return get_runtime_module()


def write_error(job_dir: Path, payload: dict[str, Any]) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "error.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_job_state(
    job_id: str,
    content: str,
    page_count: int,
    image_preset: dict[str, Any],
    image_quality: str,
    style_notes: str,
    generation_options: dict[str, Any],
    style_reference_images: list[dict[str, Any]],
    job_target: str,
    workflow_mode: str = "auto",
) -> dict[str, Any]:
    runtime = _runtime()
    normalized_workflow_mode = runtime.normalize_workflow_mode(workflow_mode)
    confirmation_policy = runtime.build_confirmation_policy(normalized_workflow_mode)
    pages = [
        {
            "page_no": index + 1,
            "title": f"第 {index + 1} 页生成中",
            "status": "pending",
            "reference_image": "",
            "element_image": "",
            "reference_prompt": "",
            "elements_prompt": "",
        }
        for index in range(page_count)
    ]
    return {
        "job_id": job_id,
        "status": "queued",
        "current_stage": "queued",
        "error": "",
        "stop_requested": False,
        "job_meta": {
            "content": content,
            "page_count": page_count,
            "image_preset": image_preset,
            "image_quality": image_quality,
            "style_notes": style_notes,
            "generation_options": generation_options,
            "style_reference_images": style_reference_images,
            "job_target": job_target,
            "job_target_label": runtime.TARGET_LABELS.get(
                job_target,
                runtime.TARGET_LABELS[runtime.JOB_TARGET_EDITABLE_PPT],
            ),
            "workflow_mode": normalized_workflow_mode,
            "workflow_mode_label": runtime.get_workflow_mode_label(normalized_workflow_mode),
            "confirmation_policy": confirmation_policy,
            "plan_confirmation": runtime.initial_plan_confirmation_state(normalized_workflow_mode),
        },
        "plan": {},
        "pages": pages,
        "reference_pages": [],
        "element_pages": [],
        "stages": [
            {
                "key": "planning",
                "label": "模型规划",
                "status": "pending",
                "summary": "等待对话模型拆解内容结构",
                "logs": [],
                "data": {},
            },
            {
                "key": "reference_generation",
                "label": "原稿图生成",
                "status": "pending",
                "summary": "等待生成带文字的 PPT 效果图",
                "logs": [],
                "data": {},
            },
            {
                "key": "elements_generation",
                "label": "元素图生成",
                "status": "pending",
                "summary": "等待生成去文字元素图",
                "logs": [],
                "data": {},
            },
            {
                "key": "ppt_export",
                "label": "可编辑元素生成",
                "status": "pending",
                "summary": "等待生成可编辑元素资源与文字脚本",
                "logs": [],
                "data": {},
            },
        ],
    }


def status_file(job_dir: Path) -> Path:
    return job_dir / "status.json"


def cache_job_state(job_id: str, state: dict[str, Any]) -> None:
    runtime = _runtime()
    with runtime.JOB_STATUS_LOCK:
        runtime.JOB_STATUS_CACHE[job_id] = state


def save_job_state(job_dir: Path, state: dict[str, Any]) -> None:
    runtime = _runtime()
    cache_job_state(state["job_id"], state)
    status_file(job_dir).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    sync_job_record(state["job_id"], state)


def load_job_state(job_id: str, job_dir: Path) -> dict[str, Any] | None:
    runtime = _runtime()
    with runtime.JOB_STATUS_LOCK:
        cached = runtime.JOB_STATUS_CACHE.get(job_id)
    if cached:
        return cached
    target = status_file(job_dir)
    if not target.exists():
        return None
    state = json.loads(target.read_text(encoding="utf-8"))
    cache_job_state(job_id, state)
    return state


def get_job_state_snapshot(job_id: str, job_dir: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    runtime = _runtime()
    record = runtime.get_job_record(runtime.JOBS_DB_PATH, job_id)
    record = reconcile_job_record(record)
    if record:
        state = record.get("state", {})
        if isinstance(state, dict) and state:
            enriched = normalize_job_state_labels(enrich_job_state_with_record(state, record))
            return runtime.attach_delivery_actions(enriched, job_dir), record
    state = load_job_state(job_id, job_dir)
    if not state:
        return None, record
    enriched = normalize_job_state_labels(enrich_job_state_with_record(state, record))
    return runtime.attach_delivery_actions(enriched, job_dir), record


def mutate_job_state(job_dir: Path, job_id: str, updater: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    runtime = _runtime()
    with runtime.JOB_STATUS_LOCK:
        current = runtime.JOB_STATUS_CACHE.get(job_id)
        if current is None:
            target = status_file(job_dir)
            if target.exists():
                current = json.loads(target.read_text(encoding="utf-8"))
            else:
                raise RuntimeError(f"找不到任务状态：{job_id}")
        state = json.loads(json.dumps(current, ensure_ascii=False))
        updater(state)
        runtime.JOB_STATUS_CACHE[job_id] = state
        status_file(job_dir).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        sync_job_record(job_id, state)
        return state


def append_stage_log(job_dir: Path, job_id: str, stage_key: str, message: str) -> None:
    def updater(state: dict[str, Any]) -> None:
        for stage in state["stages"]:
            if stage["key"] == stage_key:
                stage.setdefault("logs", []).append(message)
                break

    mutate_job_state(job_dir, job_id, updater)


def update_stage(
    job_dir: Path,
    job_id: str,
    stage_key: str,
    *,
    status: str | None = None,
    summary: str | None = None,
    data: dict[str, Any] | None = None,
    current_stage: str | None = None,
    job_status: str | None = None,
) -> None:
    def updater(state: dict[str, Any]) -> None:
        for stage in state["stages"]:
            if stage["key"] == stage_key:
                if status is not None:
                    stage["status"] = status
                if summary is not None:
                    stage["summary"] = summary
                if data is not None:
                    stage["data"] = data
                break
        if current_stage is not None:
            state["current_stage"] = current_stage
        if job_status is not None:
            state["status"] = job_status

    mutate_job_state(job_dir, job_id, updater)


def update_page_state(job_dir: Path, job_id: str, page_no: int, **fields: Any) -> None:
    def updater(state: dict[str, Any]) -> None:
        for page in state["pages"]:
            if int(page["page_no"]) == int(page_no):
                page.update(fields)
                break

    mutate_job_state(job_dir, job_id, updater)


def finalize_job_error(job_dir: Path, job_id: str, stage_key: str, payload: dict[str, Any]) -> None:
    def updater(state: dict[str, Any]) -> None:
        state["status"] = "error"
        state["current_stage"] = stage_key
        state["error"] = payload.get("error", "")
        state["stop_requested"] = False
        for stage in state["stages"]:
            if stage["key"] == stage_key:
                stage["status"] = "error"
                stage["summary"] = payload.get("error", "任务失败")
                stage.setdefault("logs", []).append(payload.get("error", "任务失败"))
                break

    mutate_job_state(job_dir, job_id, updater)
    write_error(job_dir, payload)


def finalize_job_interrupted(job_dir: Path, job_id: str, stage_key: str, message: str) -> dict[str, Any]:
    def updater(state: dict[str, Any]) -> None:
        mark_state_interrupted(state, stage_key, message)

    return mutate_job_state(job_dir, job_id, updater)


def mark_state_interrupted(state: dict[str, Any], stage_key: str, message: str) -> None:
    state["status"] = "interrupted"
    state["current_stage"] = stage_key
    state["error"] = ""
    state["stop_requested"] = False
    stages = state.get("stages", [])
    if not isinstance(stages, list):
        return
    for stage in stages:
        if not isinstance(stage, dict) or stage.get("key") != stage_key:
            continue
        logs = stage.setdefault("logs", [])
        if message not in logs:
            logs.append(message)
        stage["status"] = "interrupted"
        stage["summary"] = message
        break


def mark_job_stopping(job_dir: Path, job_id: str, stage_key: str, message: str) -> None:
    runtime = _runtime()
    record = runtime.get_job_record(runtime.JOBS_DB_PATH, job_id)
    if str((record or {}).get("status") or "").strip() == "interrupted":
        return

    def updater(state: dict[str, Any]) -> None:
        state["status"] = "stopping"
        state["current_stage"] = stage_key
        state["stop_requested"] = True
        for stage in state["stages"]:
            if stage["key"] == stage_key:
                stage["summary"] = message
                stage["status"] = "stopping"
                logs = stage.setdefault("logs", [])
                if message not in logs:
                    logs.append(message)
                break

    mutate_job_state(job_dir, job_id, updater)


def sync_job_record(job_id: str, state: dict[str, Any]) -> None:
    runtime = _runtime()
    record = runtime.get_job_record(runtime.JOBS_DB_PATH, job_id)
    if not record:
        return
    merged_result = runtime.merge_job_result(record.get("result", {}), state.get("result", {}))
    runtime.update_job_record(
        runtime.JOBS_DB_PATH,
        job_id,
        status=state.get("status", "queued"),
        current_stage=state.get("current_stage", "queued"),
        state=state,
        result=merged_result,
        stop_requested=state.get("stop_requested", False),
    )


def reconcile_stale_stopping_job(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if not is_stale_stopping_job(record):
        return record
    runtime = _runtime()
    assert record is not None
    job_id = str(record.get("job_id") or "").strip()
    job_dir = Path(str(record.get("job_dir") or ""))
    stage_key = str(record.get("current_stage") or "queued").strip() or "queued"
    message = runtime.INTERRUPTED_MESSAGE
    target = status_file(job_dir)

    if target.exists():
        finalize_job_interrupted(job_dir, job_id, stage_key, message)
    else:
        state = record.get("state", {})
        if not isinstance(state, dict):
            state = {}
        state = json.loads(json.dumps(state, ensure_ascii=False))
        state.setdefault("job_id", job_id)
        state.setdefault("stages", [])
        mark_state_interrupted(state, stage_key, message)
        job_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        cache_job_state(job_id, state)
        runtime.update_job_record(
            runtime.JOBS_DB_PATH,
            job_id,
            status="interrupted",
            current_stage=stage_key,
            state=state,
            stop_requested=False,
        )

    return runtime.get_job_record(runtime.JOBS_DB_PATH, job_id) or record


def reconcile_job_record(record: dict[str, Any] | None) -> dict[str, Any] | None:
    record = reconcile_stale_stopping_job(record)
    return reconcile_unmanaged_terminal_stage_job(record)


def reconcile_unmanaged_terminal_stage_job(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if not should_reconcile_unmanaged_terminal_stage_job(record):
        return record
    runtime = _runtime()
    assert record is not None
    job_id = str(record.get("job_id") or "").strip()
    job_dir = Path(str(record.get("job_dir") or ""))
    state = load_state_for_record_reconciliation(record, job_dir)
    if not state:
        return record

    reconciled = reconcile_job_runtime_status(state)
    if str(reconciled.get("status") or "").strip() not in STAGE_TERMINAL_STATUSES:
        return record

    job_dir.mkdir(parents=True, exist_ok=True)
    status_file(job_dir).write_text(json.dumps(reconciled, ensure_ascii=False, indent=2), encoding="utf-8")
    cache_job_state(job_id, reconciled)
    runtime.update_job_record(
        runtime.JOBS_DB_PATH,
        job_id,
        status=reconciled.get("status", "interrupted"),
        current_stage=reconciled.get("current_stage", record.get("current_stage", "")),
        state=reconciled,
        stop_requested=False,
    )
    return runtime.get_job_record(runtime.JOBS_DB_PATH, job_id) or record


def should_reconcile_unmanaged_terminal_stage_job(record: dict[str, Any] | None) -> bool:
    if not record or str(record.get("status") or "").strip() not in NON_TERMINAL_JOB_STATUSES:
        return False
    runtime = _runtime()
    job_id = str(record.get("job_id") or "").strip()
    if not job_id or runtime.is_job_managed(job_id):
        return False
    state = load_state_for_record_reconciliation(record, Path(str(record.get("job_dir") or "")))
    return bool(state and find_terminal_stage_for_runtime_status(state) is not None)


def load_state_for_record_reconciliation(record: dict[str, Any], job_dir: Path) -> dict[str, Any]:
    target = status_file(job_dir)
    if target.exists():
        try:
            state = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(state, dict):
                return state
        except (OSError, json.JSONDecodeError):
            pass
    state = record.get("state", {})
    return json.loads(json.dumps(state, ensure_ascii=False)) if isinstance(state, dict) else {}


def is_stale_stopping_job(record: dict[str, Any] | None) -> bool:
    if not record or str(record.get("status") or "").strip() != "stopping":
        return False
    runtime = _runtime()
    job_id = str(record.get("job_id") or "").strip()
    if not job_id or runtime.is_job_managed(job_id):
        return False
    updated_at = parse_job_timestamp(record.get("updated_at"))
    if updated_at is None:
        return True
    return datetime.utcnow() - updated_at >= timedelta(seconds=resolve_stale_stopping_grace_seconds())


def resolve_stale_stopping_grace_seconds() -> int:
    runtime = _runtime()
    try:
        config = runtime.read_config()
    except Exception:
        config = {}
    raw_value = config.get("stopping_grace_seconds", DEFAULT_STALE_STOPPING_GRACE_SECONDS)
    try:
        return max(1, int(raw_value))
    except (TypeError, ValueError):
        return DEFAULT_STALE_STOPPING_GRACE_SECONDS


def parse_job_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for date_format in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, date_format)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def build_job_title(content: str) -> str:
    return derive_title_from_content(content)


def _find_preview_image(state: dict[str, Any]) -> str:
    for collection_name in ("element_pages", "reference_pages", "pages"):
        collection = state.get(collection_name, [])
        if not isinstance(collection, list):
            continue
        for page in collection:
            if not isinstance(page, dict):
                continue
            for key in ("element_image", "reference_image", "image"):
                image = str(page.get(key, "")).strip()
                if image:
                    return image
    return ""


def _normalize_style_reference_images(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "")).strip()
        if not url:
            continue
        normalized.append(
            {
                "name": str(item.get("name", "")).strip(),
                "url": url,
                "size": _normalize_file_size(item.get("size")),
            }
        )
    return normalized


def _normalize_file_size(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _find_style_reference_images(record: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
    job_meta = state.get("job_meta", {})
    if isinstance(job_meta, dict):
        from_state = _normalize_style_reference_images(job_meta.get("style_reference_images"))
        if from_state:
            return from_state

    request_payload = record.get("request", {})
    if isinstance(request_payload, dict):
        from_request = _normalize_style_reference_images(request_payload.get("style_reference_images"))
        if from_request:
            return from_request

    job_dir = str(record.get("job_dir") or "").strip()
    job_id = str(record.get("job_id") or "").strip()
    if not job_dir or not job_id:
        return []
    return _normalize_style_reference_images(_runtime().list_style_reference_images(job_id, Path(job_dir)))


def _summarize_stage_progress(state: dict[str, Any]) -> list[dict[str, Any]]:
    stages = state.get("stages", [])
    if not isinstance(stages, list):
        return []
    runtime = _runtime()
    summarized: list[dict[str, Any]] = []
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        key = str(stage.get("key") or "").strip()
        summarized.append(
            {
                "key": key,
                "label": runtime.normalize_stage_label(key, stage.get("label")),
                "status": str(stage.get("status") or "").strip(),
                "summary": str(stage.get("summary") or "").strip(),
            }
        )
    return summarized


def job_summary(record: dict[str, Any]) -> dict[str, Any]:
    state = record.get("state", {}) if isinstance(record.get("state"), dict) else {}
    job_meta = state.get("job_meta", {}) if isinstance(state.get("job_meta"), dict) else {}
    request_payload = record.get("request", {}) if isinstance(record.get("request"), dict) else {}
    workflow_mode = _runtime().normalize_workflow_mode(
        job_meta.get("workflow_mode") or request_payload.get("workflow_mode")
    )
    return {
        "job_id": record["job_id"],
        "title": record["title"],
        "status": record["status"],
        "current_stage": record["current_stage"],
        "page_count": record["page_count"],
        "image_preset": record["image_preset"],
        "image_quality": record["image_quality"],
        "style_notes": record["style_notes"],
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "pinned_at": str(record.get("pinned_at") or ""),
        "stop_requested": record.get("stop_requested", False),
        "stages": _summarize_stage_progress(state),
        "preview_image": _find_preview_image(state),
        "style_reference_images": _find_style_reference_images(record, state),
        "workflow_mode": workflow_mode,
        "workflow_mode_label": _runtime().get_workflow_mode_label(workflow_mode),
    }


def enrich_job_state_with_record(state: dict[str, Any], record: dict[str, Any] | None) -> dict[str, Any]:
    runtime = _runtime()
    merged = json.loads(json.dumps(state, ensure_ascii=False))
    if not record:
        runtime.ensure_workflow_metadata(merged)
        return normalize_job_state_labels(reconcile_job_runtime_status(merged))
    merge_record_runtime_fields(merged, record)
    merged["title"] = str(record.get("title") or merged.get("title") or "")
    merged["pinned_at"] = str(record.get("pinned_at") or "")
    job_meta = merged.setdefault("job_meta", {})
    runtime.ensure_workflow_metadata(merged, record.get("request", {}))
    job_meta["content"] = str(job_meta.get("content") or record.get("content") or "")
    job_meta["page_count"] = int(job_meta.get("page_count") or record.get("page_count") or 0)
    job_meta["image_quality"] = str(job_meta.get("image_quality") or record.get("image_quality") or "")
    job_meta["style_notes"] = str(job_meta.get("style_notes") or record.get("style_notes") or "")
    job_target = runtime.normalize_job_target(
        job_meta.get("job_target") or record.get("request", {}).get("job_target"),
        runtime.JOB_TARGET_EDITABLE_PPT,
    )
    job_meta["job_target"] = job_target
    job_meta["job_target_label"] = runtime.TARGET_LABELS.get(job_target, runtime.TARGET_LABELS[runtime.JOB_TARGET_EDITABLE_PPT])
    if not isinstance(job_meta.get("generation_options"), dict):
        job_meta["generation_options"] = runtime.resolve_generation_options(record.get("request", {}), config=runtime.read_config())
    if not job_meta.get("image_preset"):
        config = runtime.read_config()
        try:
            job_meta["image_preset"] = runtime.resolve_image_preset(config, str(record.get("image_preset") or ""))
        except ValueError:
            job_meta["image_preset"] = {
                "name": str(record.get("image_preset") or ""),
                "label": str(record.get("image_preset") or ""),
            }
    if not isinstance(job_meta.get("style_reference_images"), list) or not job_meta.get("style_reference_images"):
        job_meta["style_reference_images"] = runtime.list_style_reference_images(str(record["job_id"]), Path(record["job_dir"]))
    return normalize_job_state_labels(reconcile_job_runtime_status(merged))


def merge_record_runtime_fields(state: dict[str, Any], record: dict[str, Any]) -> None:
    for field in RUNTIME_STATE_FIELDS:
        if field in record:
            state[field] = record[field]


def reconcile_job_runtime_status(state: dict[str, Any]) -> dict[str, Any]:
    status = str(state.get("status", "")).strip()
    if status not in NON_TERMINAL_JOB_STATUSES:
        return state
    terminal_stage = find_terminal_stage_for_runtime_status(state)
    if not terminal_stage:
        return state

    terminal_status = str(terminal_stage.get("status", "")).strip()
    state["status"] = terminal_status
    state["current_stage"] = str(terminal_stage.get("key") or state.get("current_stage") or "")
    state["stop_requested"] = False
    if terminal_status == "error" and not str(state.get("error", "")).strip():
        state["error"] = str(terminal_stage.get("summary") or "")
    return state


def find_terminal_stage_for_runtime_status(state: dict[str, Any]) -> dict[str, Any] | None:
    current_stage_key = str(state.get("current_stage") or "").strip()
    stages = state.get("stages", [])
    if not isinstance(stages, list):
        return None
    if current_stage_key:
        for stage in stages:
            if not isinstance(stage, dict) or str(stage.get("key") or "").strip() != current_stage_key:
                continue
            return stage if str(stage.get("status", "")).strip() in STAGE_TERMINAL_STATUSES else None
        return None
    return find_first_stage_with_status(state, STAGE_TERMINAL_STATUSES)


def find_first_stage_with_status(state: dict[str, Any], statuses: set[str]) -> dict[str, Any] | None:
    stages = state.get("stages", [])
    if not isinstance(stages, list):
        return None
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        if str(stage.get("status", "")).strip() in statuses:
            return stage
    return None


def normalize_job_state_labels(state: dict[str, Any]) -> dict[str, Any]:
    runtime = _runtime()
    stages = state.get("stages", [])
    if not isinstance(stages, list):
        return state
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        stage["label"] = runtime.normalize_stage_label(stage.get("key"), stage.get("label"))
    return state


def list_job_summaries(limit: int = 100) -> list[dict[str, Any]]:
    runtime = _runtime()
    records = [
        reconcile_job_record(record) or record
        for record in runtime.list_job_records(runtime.JOBS_DB_PATH, limit=limit)
    ]
    return [job_summary(record) for record in records]


def should_stop_job(job_id: str) -> bool:
    runtime = _runtime()
    record = runtime.get_job_record(runtime.JOBS_DB_PATH, job_id)
    if bool(record and record.get("stop_requested")):
        return True
    if not record:
        return False
    return runtime.has_job_stop_request(Path(str(record.get("job_dir") or "")), job_id)


def remove_job_artifacts(job_dir: Path) -> None:
    runtime = _runtime()
    if not job_dir.exists():
        return
    try:
        resolved = job_dir.resolve()
    except OSError:
        return
    config = runtime.read_config()
    output_root = (runtime.ROOT / str(config.get("output_dir", "output"))).resolve()
    if resolved == output_root or output_root not in resolved.parents:
        return
    shutil.rmtree(resolved, ignore_errors=True)


def ensure_job_not_stopped(job_dir: Path, job_id: str, stage_key: str) -> None:
    runtime = _runtime()
    if should_stop_job(job_id):
        record = runtime.get_job_record(runtime.JOBS_DB_PATH, job_id) or {}
        if str(record.get("status") or "").strip() != "interrupted":
            mark_job_stopping(job_dir, job_id, stage_key, runtime.STOPPING_MESSAGE)
        raise runtime.JobInterruptedError(stage_key)


def _attach_page_evaluations(plan: dict[str, Any], evaluation_result: dict[str, Any]) -> None:
    page_scores = evaluation_result.get("page_scores", [])
    score_map: dict[int, dict[str, Any]] = {}
    for ps in page_scores:
        score_map[int(ps.get("page_no", 0))] = ps
    for page in plan.get("pages", []):
        page_no = int(page.get("page_no", 0))
        if page_no in score_map:
            page["evaluation"] = score_map[page_no]


def extract_pages_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for page in state.get("pages", []):
        pages.append(
            {
                "page_no": int(page["page_no"]),
                "title": page.get("title", f"第 {page['page_no']} 页"),
                "summary": page.get("summary", ""),
                "bullets": page.get("bullets", []),
                "layout_intent": page.get("layout_intent", ""),
                "layout_family": page.get("layout_family", ""),
                "element_plan": page.get("element_plan", []),
                "reference_mode": page.get("reference_mode", "generation"),
                "prompt_profile": page.get("prompt_profile", "compressed"),
                "image_prompt": page.get("reference_prompt", ""),
                "elements_prompt": page.get("elements_prompt", ""),
                "layout_slots": page.get("layout_slots", []),
                "texts": page.get("texts", []),
            }
        )
    return pages


def extract_reference_pages_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    references = list(state.get("reference_pages", []))
    if references:
        return references

    rebuilt: list[dict[str, Any]] = []
    for page in state.get("pages", []):
        reference_image = str(page.get("reference_image", "")).strip()
        if not reference_image:
            continue
        rebuilt.append(
            {
                "page_no": int(page["page_no"]),
                "title": page.get("title", f"第 {page['page_no']} 页"),
                "prompt": page.get("reference_prompt", ""),
                "image": reference_image,
                "generation": {},
            }
        )
    rebuilt.sort(key=lambda item: int(item["page_no"]))
    return rebuilt


def extract_element_pages_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    elements = list(state.get("element_pages", []))
    if elements:
        return elements

    rebuilt: list[dict[str, Any]] = []
    for page in state.get("pages", []):
        element_image = str(page.get("element_image", "")).strip()
        if not element_image:
            continue
        rebuilt.append(
            {
                "page_no": int(page["page_no"]),
                "prompt": page.get("elements_prompt", ""),
                "image": element_image,
                "generation": {},
            }
        )
    rebuilt.sort(key=lambda item: int(item["page_no"]))
    return rebuilt


def get_job_target_from_state(state: dict[str, Any]) -> str:
    runtime = _runtime()
    return runtime.normalize_job_target(
        state.get("job_meta", {}).get("job_target"),
        runtime.JOB_TARGET_EDITABLE_PPT,
    )


def finalize_job_completed(
    job_dir: Path,
    job_id: str,
    state: dict[str, Any],
    result_payload: dict[str, Any],
    *,
    terminal_stage: str,
    summary: str,
) -> None:
    runtime = _runtime()
    job_target = get_job_target_from_state(state)
    normalized_result = runtime.normalize_job_result_payload(result_payload)
    deliveries = normalized_result.get("deliveries", {})

    def updater(current_state: dict[str, Any]) -> None:
        current_state["status"] = "completed"
        current_state["current_stage"] = terminal_stage
        current_state["result"] = normalized_result
        current_state["stop_requested"] = False
        current_state["error"] = ""

    mutate_job_state(job_dir, job_id, updater)
    update_stage(
        job_dir,
        job_id,
        terminal_stage,
        status="completed",
        summary=summary,
        data=deliveries if isinstance(deliveries, dict) else {},
        current_stage=terminal_stage,
        job_status="completed",
    )
    append_stage_log(job_dir, job_id, terminal_stage, runtime.build_completion_summary(job_target))
    runtime.update_job_record(
        runtime.JOBS_DB_PATH,
        job_id,
        stop_requested=False,
        status="completed",
        current_stage=terminal_stage,
        result=normalized_result,
    )


def reconcile_resume_state(job_dir: Path, job_id: str) -> dict[str, Any]:
    runtime = _runtime()

    def updater(state: dict[str, Any]) -> None:
        pages = extract_pages_from_state(state)
        references = extract_reference_pages_from_state(state)
        elements = extract_element_pages_from_state(state)
        job_target = get_job_target_from_state(state)
        completion_map = {
            "planning": runtime.has_complete_planning_state(state),
            "reference_generation": runtime.has_expected_outputs(references, len(pages)),
            "elements_generation": runtime.has_expected_outputs(elements, len(references)),
            "ppt_export": bool(runtime.get_editable_delivery_bundle(state.get("result", {}))),
        }
        runtime.reconcile_completed_stages(state, completion_map)
        if not runtime.should_continue_after_stage(job_target, "reference_generation"):
            for stage in state.get("stages", []):
                if stage.get("key") in {"elements_generation", "ppt_export"} and stage.get("status") == "pending":
                    stage["status"] = "skipped"
                    stage["summary"] = "当前输出模式截至原稿图阶段，此阶段已跳过"

    return mutate_job_state(job_dir, job_id, updater)


def prepare_state_for_resume(state: dict[str, Any], next_job_target: str) -> None:
    runtime = _runtime()
    previous_stage_key = str(state.get("current_stage") or "").strip()
    state["stop_requested"] = False
    state["status"] = "queued"
    state["error"] = ""
    job_meta = state.setdefault("job_meta", {})
    job_meta["job_target"] = next_job_target
    job_meta["job_target_label"] = runtime.TARGET_LABELS[next_job_target]

    stages = state.get("stages", [])
    if not isinstance(stages, list):
        return
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        stage_key = str(stage.get("key") or "").strip()
        stage_status = str(stage.get("status") or "").strip()
        if stage_key == previous_stage_key and stage_status in RESUMABLE_STAGE_STATUSES:
            stage["status"] = "pending"
            stage["summary"] = "等待继续执行"
        if stage_key in {"elements_generation", "ppt_export"} and stage_status == "skipped":
            stage["status"] = "pending"
            stage["summary"] = "等待继续执行"
