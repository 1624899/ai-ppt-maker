from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def find_stage(state: dict[str, Any], stage_key: str) -> dict[str, Any]:
    for stage in state.get("stages", []):
        if stage.get("key") == stage_key:
            return stage
    return {}


def is_stage_completed(state: dict[str, Any], stage_key: str) -> bool:
    return str(find_stage(state, stage_key).get("status", "")) == "completed"


def has_expected_outputs(items: Sequence[Any], expected_count: int) -> bool:
    if expected_count <= 0:
        return False
    return len(items) >= expected_count


def should_run_stage(
    state: dict[str, Any],
    stage_key: str,
    *,
    output_ready: bool,
) -> bool:
    return (not is_stage_completed(state, stage_key)) or (not output_ready)


def reconcile_completed_stages(
    state: dict[str, Any],
    completion_map: dict[str, bool],
) -> bool:
    changed = False
    for stage in state.get("stages", []):
        stage_key = str(stage.get("key", ""))
        if not completion_map.get(stage_key):
            continue
        if str(stage.get("status", "")) == "completed":
            continue
        stage["status"] = "completed"
        changed = True
    return changed
