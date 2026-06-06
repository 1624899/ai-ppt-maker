from __future__ import annotations

from typing import Any, Iterable

from ppt_system.jobs.job_targets import get_terminal_stage, normalize_job_target
from ppt_system.runtime.time_utils import utc_iso_timestamp


STAGE_ORDER = (
    "planning",
    "reference_generation",
    "elements_generation",
    "ppt_export",
)


def reset_stages_after_artifact_change(
    state: dict[str, Any],
    *,
    changed_stage: str,
    page_numbers: Iterable[int] = (),
    summary: str,
    include_changed_stage: bool = False,
) -> None:
    """根据被替换的阶段产物，统一重置需要重新执行的后续阶段。"""
    affected_stages = _affected_stage_keys(
        state,
        changed_stage=changed_stage,
        include_changed_stage=include_changed_stage,
    )
    if not affected_stages:
        return

    first_stage = affected_stages[0]
    state["status"] = "queued"
    state["current_stage"] = first_stage
    state["error"] = ""
    state["stop_requested"] = False

    page_scope = _format_page_scope(page_numbers)
    log_message = f"{page_scope}图片产物已更新，等待重新生成后续结果"
    now = utc_iso_timestamp()
    for stage in state.get("stages", []):
        if not isinstance(stage, dict) or stage.get("key") not in affected_stages:
            continue
        stage["status"] = "pending"
        stage["summary"] = summary
        stage["updated_at"] = now
        logs = stage.setdefault("logs", [])
        if isinstance(logs, list):
            logs.append(log_message)


def _affected_stage_keys(
    state: dict[str, Any],
    *,
    changed_stage: str,
    include_changed_stage: bool,
) -> list[str]:
    try:
        changed_index = STAGE_ORDER.index(changed_stage)
    except ValueError:
        return []
    start_index = changed_index if include_changed_stage else changed_index + 1
    existing_stage_keys = {
        str(stage.get("key") or "")
        for stage in state.get("stages", [])
        if isinstance(stage, dict)
    }
    terminal_stage = _terminal_stage_for_state(state)
    try:
        terminal_index = STAGE_ORDER.index(terminal_stage)
    except ValueError:
        terminal_index = len(STAGE_ORDER) - 1
    return [
        stage_key
        for stage_key in STAGE_ORDER[start_index : terminal_index + 1]
        if stage_key in existing_stage_keys
    ]


def _terminal_stage_for_state(state: dict[str, Any]) -> str:
    job_meta = state.get("job_meta", {}) if isinstance(state.get("job_meta"), dict) else {}
    return get_terminal_stage(normalize_job_target(job_meta.get("job_target")))


def _format_page_scope(page_numbers: Iterable[int]) -> str:
    normalized = sorted({int(page_no) for page_no in page_numbers if int(page_no) > 0})
    if not normalized:
        return "任务"
    if len(normalized) == 1:
        return f"第 {normalized[0]} 页"
    preview = "、".join(str(page_no) for page_no in normalized[:6])
    suffix = "等页面" if len(normalized) > 6 else "页"
    return f"第 {preview} {suffix}"
