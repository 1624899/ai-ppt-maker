from __future__ import annotations

from typing import Any


JOB_TARGET_REFERENCE_ONLY = "reference_only"
JOB_TARGET_EDITABLE_PPT = "editable_ppt"

JOB_TARGETS = {
    JOB_TARGET_REFERENCE_ONLY,
    JOB_TARGET_EDITABLE_PPT,
}

STAGE_REFERENCE_GENERATION = "reference_generation"
STAGE_ELEMENTS_GENERATION = "elements_generation"
STAGE_PPT_EXPORT = "ppt_export"

TERMINAL_STAGE_BY_TARGET = {
    JOB_TARGET_REFERENCE_ONLY: STAGE_REFERENCE_GENERATION,
    JOB_TARGET_EDITABLE_PPT: STAGE_PPT_EXPORT,
}

TARGET_LABELS = {
    JOB_TARGET_REFERENCE_ONLY: "图片版 PPT",
    JOB_TARGET_EDITABLE_PPT: "可编辑 PPT",
}


def normalize_job_target(value: Any, default: str = JOB_TARGET_EDITABLE_PPT) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in JOB_TARGETS:
        return normalized
    return default


def get_terminal_stage(job_target: Any) -> str:
    normalized = normalize_job_target(job_target)
    return TERMINAL_STAGE_BY_TARGET[normalized]


def is_reference_only_target(job_target: Any) -> bool:
    return normalize_job_target(job_target) == JOB_TARGET_REFERENCE_ONLY


def should_continue_after_stage(job_target: Any, stage_key: str) -> bool:
    terminal_stage = get_terminal_stage(job_target)
    stage_order = [
        STAGE_REFERENCE_GENERATION,
        STAGE_ELEMENTS_GENERATION,
        STAGE_PPT_EXPORT,
    ]
    try:
        return stage_order.index(stage_key) < stage_order.index(terminal_stage)
    except ValueError:
        return True


def can_upgrade_to_editable(job_state: dict[str, Any] | None) -> bool:
    if not isinstance(job_state, dict):
        return False
    job_meta = job_state.get("job_meta", {})
    if normalize_job_target(job_meta.get("job_target")) != JOB_TARGET_REFERENCE_ONLY:
        return False
    return str(job_state.get("status", "")).strip() == "completed"


def build_completion_summary(job_target: Any) -> str:
    normalized = normalize_job_target(job_target)
    if normalized == JOB_TARGET_REFERENCE_ONLY:
        return "参考图与图片版 PPT 已生成完成，可按需继续转换为可编辑 PPT。"
    return "可编辑 PPT 已生成完成，可直接下载。"
