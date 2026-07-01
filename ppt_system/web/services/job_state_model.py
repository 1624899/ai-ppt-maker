from __future__ import annotations

import json
from typing import Any

from ppt_system.export.stage_labels import normalize_stage_label
from ppt_system.generation.title_extraction import derive_title_from_content
from ppt_system.jobs.job_targets import JOB_TARGET_EDITABLE_PPT, TARGET_LABELS, normalize_job_target
from ppt_system.web.services.workflow_policy import (
    build_confirmation_policy,
    get_workflow_mode_label,
    initial_plan_confirmation_state,
    normalize_workflow_mode,
)

RUNTIME_STATE_FIELDS = ("status", "current_stage", "stop_requested")
NON_TERMINAL_JOB_STATUSES = {"", "pending", "queued", "running", "stopping"}
NON_TERMINAL_JOB_STATUSES.add("awaiting_plan_confirmation")
STAGE_TERMINAL_STATUSES = {"error", "interrupted"}
RESUMABLE_STAGE_STATUSES = STAGE_TERMINAL_STATUSES | {"stopping"}
DEFAULT_STALE_STOPPING_GRACE_SECONDS = 300

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
    normalized_workflow_mode = normalize_workflow_mode(workflow_mode)
    confirmation_policy = build_confirmation_policy(normalized_workflow_mode)
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
            "job_target_label": TARGET_LABELS.get(
                job_target,
                TARGET_LABELS[JOB_TARGET_EDITABLE_PPT],
            ),
            "workflow_mode": normalized_workflow_mode,
            "workflow_mode_label": get_workflow_mode_label(normalized_workflow_mode),
            "confirmation_policy": confirmation_policy,
            "plan_confirmation": initial_plan_confirmation_state(normalized_workflow_mode),
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

def build_job_title(content: str) -> str:
    return derive_title_from_content(content)

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
    return normalize_job_target(
        state.get("job_meta", {}).get("job_target"),
        JOB_TARGET_EDITABLE_PPT,
    )

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

def prepare_state_for_resume(state: dict[str, Any], next_job_target: str) -> None:
    previous_stage_key = str(state.get("current_stage") or "").strip()
    state["stop_requested"] = False
    state["status"] = "queued"
    state["error"] = ""
    job_meta = state.setdefault("job_meta", {})
    job_meta["job_target"] = next_job_target
    job_meta["job_target_label"] = TARGET_LABELS[next_job_target]

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
    stages = state.get("stages", [])
    if not isinstance(stages, list):
        return state
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        stage["label"] = normalize_stage_label(stage.get("key"), stage.get("label"))
    return state
