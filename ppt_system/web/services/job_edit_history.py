from __future__ import annotations

from typing import Any, Mapping

from ppt_system.web.services.job_plan_record_sync import resolve_current_style_notes


def _find_model_plan(versions: list[Any]) -> Mapping[str, Any] | None:
    for version in versions:
        if not isinstance(version, Mapping) or str(version.get("source") or "") != "model":
            continue
        plan = version.get("plan")
        if isinstance(plan, Mapping):
            return plan
    return None


def build_job_edit_summary(state: Mapping[str, Any], record: Mapping[str, Any]) -> dict[str, Any]:
    """生成历史列表所需的编辑状态摘要。"""
    versions = state.get("plan_versions", []) if isinstance(state.get("plan_versions"), list) else []
    model_plan = _find_model_plan(versions)
    user_versions = [
        version
        for version in versions
        if (
            isinstance(version, Mapping)
            and str(version.get("source") or "").startswith("user_")
            and (model_plan is None or version.get("plan") != model_plan)
        )
    ]
    operations = state.get("operations", []) if isinstance(state.get("operations"), list) else []
    completed_operations = [
        operation
        for operation in operations
        if isinstance(operation, Mapping)
        and str(operation.get("status") or "").lower() == "completed"
    ]
    latest_candidates = [*user_versions, *completed_operations]
    latest = max(
        latest_candidates,
        key=lambda item: str(item.get("created_at") or item.get("updated_at") or ""),
        default={},
    )
    return {
        "style_notes": resolve_current_style_notes(state, record),
        "has_user_edits": bool(user_versions or completed_operations),
        "edit_count": len(user_versions) + len(completed_operations),
        "last_edit_summary": str(latest.get("summary") or latest.get("message") or latest.get("label") or "").strip(),
        "last_edited_at": str(latest.get("created_at") or latest.get("updated_at") or "").strip(),
    }
