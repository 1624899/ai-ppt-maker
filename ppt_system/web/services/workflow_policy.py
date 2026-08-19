from __future__ import annotations

from typing import Any, Mapping

from ppt_system.runtime.time_utils import utc_iso_timestamp


WORKFLOW_MODE_AUTO = "auto"
WORKFLOW_MODE_GUIDED = "guided"
WORKFLOW_MODES = {WORKFLOW_MODE_AUTO, WORKFLOW_MODE_GUIDED}

WORKFLOW_MODE_LABELS = {
    WORKFLOW_MODE_AUTO: "一键生成",
    WORKFLOW_MODE_GUIDED: "分步规划",
}

AWAITING_PLAN_CONFIRMATION_STATUS = "awaiting_plan_confirmation"
AWAITING_REFERENCE_CONFIRMATION_STATUS = "awaiting_reference_confirmation"


def normalize_workflow_mode(value: Any, default: str = WORKFLOW_MODE_AUTO) -> str:
    """归一化工作流模式，避免接口层散落模式判断。"""
    normalized = str(value or "").strip().lower()
    if normalized in WORKFLOW_MODES:
        return normalized
    return default


def get_workflow_mode_label(value: Any) -> str:
    return WORKFLOW_MODE_LABELS[normalize_workflow_mode(value)]


def build_confirmation_policy(
    workflow_mode: Any,
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, bool]:
    """根据工作流模式生成阶段确认策略。"""
    normalized_mode = normalize_workflow_mode(workflow_mode)
    policy = {
        "plan": normalized_mode == WORKFLOW_MODE_GUIDED,
        "reference_pages": normalized_mode == WORKFLOW_MODE_GUIDED,
        "element_pages": False,
        "export": False,
    }
    if isinstance(overrides, Mapping):
        for key in policy:
            if key in overrides:
                policy[key] = bool(overrides[key])
    return policy


def initial_plan_confirmation_state(workflow_mode: Any) -> dict[str, Any]:
    required = build_confirmation_policy(workflow_mode)["plan"]
    return {
        "required": required,
        "confirmed": not required,
        "status": "pending" if required else "not_required",
        "updated_at": _utc_timestamp(),
    }


def ensure_workflow_metadata(
    state: dict[str, Any],
    request_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """为旧任务或测试状态补齐工作流元信息。"""
    request_payload = request_payload or {}
    job_meta = state.setdefault("job_meta", {})
    workflow_mode = normalize_workflow_mode(
        job_meta.get("workflow_mode") or request_payload.get("workflow_mode")
    )
    job_meta["workflow_mode"] = workflow_mode
    job_meta["workflow_mode_label"] = get_workflow_mode_label(workflow_mode)

    raw_policy = job_meta.get("confirmation_policy")
    job_meta["confirmation_policy"] = build_confirmation_policy(
        workflow_mode,
        raw_policy if isinstance(raw_policy, Mapping) else None,
    )

    confirmation = job_meta.get("plan_confirmation")
    if not isinstance(confirmation, dict):
        confirmation = initial_plan_confirmation_state(workflow_mode)
    confirmation["required"] = bool(job_meta["confirmation_policy"]["plan"])
    if not confirmation["required"]:
        confirmation["confirmed"] = True
        confirmation["status"] = "not_required"
    else:
        confirmation["confirmed"] = bool(confirmation.get("confirmed"))
        confirmation["status"] = str(
            confirmation.get("status")
            or ("confirmed" if confirmation["confirmed"] else "pending")
        )
    confirmation["updated_at"] = str(confirmation.get("updated_at") or _utc_timestamp())
    job_meta["plan_confirmation"] = confirmation
    reference_confirmation = job_meta.get("reference_confirmation")
    if not isinstance(reference_confirmation, dict):
        required = bool(job_meta["confirmation_policy"]["reference_pages"])
        # 旧任务若已有下游产物，说明原稿阶段实际上已经通过，不能因新增确认关卡阻断重新导出。
        downstream_completed = _has_existing_downstream_outputs(state)
        confirmed = not required or downstream_completed
        reference_confirmation = {
            "required": required,
            "confirmed": confirmed,
            "status": "inferred_from_existing_outputs" if required and downstream_completed else ("pending" if required else "not_required"),
            "updated_at": _utc_timestamp(),
        }
    job_meta["reference_confirmation"] = reference_confirmation
    return state


def _has_existing_downstream_outputs(state: Mapping[str, Any]) -> bool:
    elements = state.get("element_pages", [])
    if isinstance(elements, list) and any(isinstance(item, Mapping) and item.get("image") for item in elements):
        return True
    for stage in state.get("stages", []):
        if not isinstance(stage, Mapping):
            continue
        if stage.get("key") in {"elements_generation", "ppt_export"} and stage.get("status") == "completed":
            return True
    return False


def get_workflow_mode_from_state(state: Mapping[str, Any]) -> str:
    job_meta = state.get("job_meta", {})
    if not isinstance(job_meta, Mapping):
        return WORKFLOW_MODE_AUTO
    return normalize_workflow_mode(job_meta.get("workflow_mode"))


def requires_plan_confirmation(state: Mapping[str, Any]) -> bool:
    job_meta = state.get("job_meta", {})
    if not isinstance(job_meta, Mapping):
        return False
    policy = job_meta.get("confirmation_policy")
    if isinstance(policy, Mapping) and "plan" in policy:
        return bool(policy.get("plan"))
    return get_workflow_mode_from_state(state) == WORKFLOW_MODE_GUIDED


def is_plan_confirmed(state: Mapping[str, Any]) -> bool:
    job_meta = state.get("job_meta", {})
    if not isinstance(job_meta, Mapping):
        return False
    confirmation = job_meta.get("plan_confirmation")
    if isinstance(confirmation, Mapping):
        return bool(confirmation.get("confirmed"))
    return not requires_plan_confirmation(state)


def should_pause_after_planning(state: Mapping[str, Any]) -> bool:
    return requires_plan_confirmation(state) and not is_plan_confirmed(state)


def mark_awaiting_plan_confirmation(state: dict[str, Any]) -> None:
    """把任务切到规划待确认状态，后续阶段保持可恢复。"""
    ensure_workflow_metadata(state)
    state["status"] = AWAITING_PLAN_CONFIRMATION_STATUS
    state["current_stage"] = "planning"
    state["stop_requested"] = False
    state["error"] = ""
    confirmation = state.setdefault("job_meta", {}).setdefault("plan_confirmation", {})
    confirmation.update(
        {
            "required": True,
            "confirmed": False,
            "status": "awaiting_confirmation",
            "updated_at": _utc_timestamp(),
        }
    )


def mark_plan_confirmed(state: dict[str, Any]) -> None:
    ensure_workflow_metadata(state)
    confirmation = state.setdefault("job_meta", {}).setdefault("plan_confirmation", {})
    confirmation.update(
        {
            "required": bool(state["job_meta"]["confirmation_policy"].get("plan")),
            "confirmed": True,
            "status": "confirmed",
            "confirmed_at": _utc_timestamp(),
            "updated_at": _utc_timestamp(),
        }
    )


def mark_plan_draft(state: dict[str, Any]) -> None:
    ensure_workflow_metadata(state)
    state.setdefault("job_meta", {}).setdefault("confirmation_policy", {})["plan"] = True
    confirmation = state["job_meta"].setdefault("plan_confirmation", {})
    confirmation.update(
        {
            "required": True,
            "confirmed": False,
            "status": "draft",
            "updated_at": _utc_timestamp(),
        }
    )


def should_pause_after_reference(state: Mapping[str, Any]) -> bool:
    ensure_workflow_metadata(state)
    meta = state.get("job_meta", {})
    required = bool(meta.get("confirmation_policy", {}).get("reference_pages"))
    return required and not bool(meta.get("reference_confirmation", {}).get("confirmed"))


def mark_awaiting_reference_confirmation(state: dict[str, Any]) -> None:
    ensure_workflow_metadata(state)
    state["status"] = AWAITING_REFERENCE_CONFIRMATION_STATUS
    state["current_stage"] = "reference_generation"
    state["stop_requested"] = False
    state.setdefault("job_meta", {}).setdefault("reference_confirmation", {}).update({"required": True, "confirmed": False, "status": "awaiting_confirmation", "updated_at": _utc_timestamp()})


def mark_reference_confirmed(state: dict[str, Any]) -> None:
    ensure_workflow_metadata(state)
    state.setdefault("job_meta", {}).setdefault("reference_confirmation", {}).update({"required": True, "confirmed": True, "status": "confirmed", "confirmed_at": _utc_timestamp(), "updated_at": _utc_timestamp()})


def _utc_timestamp() -> str:
    return utc_iso_timestamp()
