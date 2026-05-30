from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Callable

from ppt_system.web.runtime import get_runtime_module


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
) -> dict[str, Any]:
    runtime = _runtime()
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
        for stage in state["stages"]:
            if stage["key"] == stage_key:
                stage["status"] = "error"
                stage.setdefault("logs", []).append(payload.get("error", "任务失败"))
                break

    mutate_job_state(job_dir, job_id, updater)
    write_error(job_dir, payload)


def finalize_job_interrupted(job_dir: Path, job_id: str, stage_key: str, message: str) -> None:
    def updater(state: dict[str, Any]) -> None:
        state["status"] = "interrupted"
        state["current_stage"] = stage_key
        state["error"] = ""
        state["stop_requested"] = False
        for stage in state["stages"]:
            if stage["key"] == stage_key and message not in stage.setdefault("logs", []):
                stage["logs"].append(message)
                stage["status"] = "interrupted"
                break

    mutate_job_state(job_dir, job_id, updater)


def mark_job_stopping(job_dir: Path, job_id: str, stage_key: str, message: str) -> None:
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


def build_job_title(content: str) -> str:
    text = " ".join(content.split())
    return text[:36] + ("..." if len(text) > 36 else "")


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


def job_summary(record: dict[str, Any]) -> dict[str, Any]:
    state = record.get("state", {})
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
        "stop_requested": record.get("stop_requested", False),
        "preview_image": _find_preview_image(state),
    }


def enrich_job_state_with_record(state: dict[str, Any], record: dict[str, Any] | None) -> dict[str, Any]:
    runtime = _runtime()
    merged = json.loads(json.dumps(state, ensure_ascii=False))
    if not record:
        return normalize_job_state_labels(merged)
    job_meta = merged.setdefault("job_meta", {})
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
    return normalize_job_state_labels(merged)


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
    return [job_summary(record) for record in runtime.list_job_records(runtime.JOBS_DB_PATH, limit=limit)]


def should_stop_job(job_id: str) -> bool:
    runtime = _runtime()
    record = runtime.get_job_record(runtime.JOBS_DB_PATH, job_id)
    return bool(record and record.get("stop_requested"))


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
