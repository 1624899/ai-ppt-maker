from __future__ import annotations

from typing import Any


RUNNING_JOB_STATUSES = frozenset({"queued", "running", "stopping"})
TERMINAL_STAGE_STATUSES = frozenset({"completed", "skipped", "error", "interrupted"})
RUNNING_STAGE_STATUSES = frozenset({"running", "stopping"})
STOPPING_MESSAGE = "暂停请求已发送，正在等待当前步骤收尾"
INTERRUPTED_MESSAGE = "任务已暂停，可继续从当前进度恢复"


def is_running_job_status(status: str) -> bool:
    return str(status or "").strip() in RUNNING_JOB_STATUSES


def normalize_orphaned_job_state(
    state: dict[str, Any],
    *,
    current_stage_key: str = "",
    resume_message: str,
) -> bool:
    """
    把失去运行上下文的任务恢复为可继续状态。

    只修正根状态和仍处于运行态的阶段，避免把已完成阶段误回退。
    """
    changed = False
    status = str(state.get("status") or "").strip()
    if is_running_job_status(status) and status != "interrupted":
        state["status"] = "interrupted"
        changed = True

    if bool(state.get("stop_requested")):
        state["stop_requested"] = False
        changed = True

    stages = state.get("stages", [])
    if not isinstance(stages, list):
        return changed

    target_stage = _find_target_stage(stages, current_stage_key or str(state.get("current_stage") or "").strip())
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        stage_status = str(stage.get("status") or "").strip()
        if stage_status not in RUNNING_STAGE_STATUSES:
            continue
        stage["status"] = "interrupted"
        changed = True

    if target_stage is None:
        return changed

    if str(target_stage.get("status") or "").strip() not in TERMINAL_STAGE_STATUSES:
        target_stage["status"] = "interrupted"
        changed = True
    if target_stage.get("summary") != resume_message:
        target_stage["summary"] = resume_message
        changed = True
    logs = target_stage.setdefault("logs", [])
    if isinstance(logs, list) and resume_message not in logs:
        logs.append(resume_message)
        changed = True
    return changed


def _find_target_stage(stages: list[dict[str, Any]], current_stage_key: str) -> dict[str, Any] | None:
    current_stage = None
    fallback_stage = None
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        stage_key = str(stage.get("key") or "").strip()
        stage_status = str(stage.get("status") or "").strip()
        if stage_key == current_stage_key:
            current_stage = stage
        if fallback_stage is None and stage_status in RUNNING_STAGE_STATUSES:
            fallback_stage = stage
    return current_stage or fallback_stage
