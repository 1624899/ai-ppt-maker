from __future__ import annotations

from typing import Any

from ppt_system.generation.layout_profiles import get_layout_profile


def plan_deck_layouts(page_candidates: list[list[dict[str, Any]]], *, locked_families: list[str | None] | None = None) -> list[dict[str, Any]]:
    """按页面顺序选择候选，避免相邻页重复语义组和视觉构图。"""
    selected: list[dict[str, Any]] = []
    locked_families = locked_families or []
    for index, candidates in enumerate(page_candidates):
        locked = locked_families[index] if index < len(locked_families) else None
        ranked = sorted(candidates, key=lambda item: item.get("score", 0), reverse=True)
        if locked:
            ranked.sort(key=lambda item: item.get("value") != locked)
        previous = selected[-1] if selected else None
        chosen = next((item for item in ranked if _compatible(item, previous)), ranked[0] if ranked else {})
        if previous and chosen:
            reason = chosen.setdefault("reason", {})
            reason["deck_fit"] = "与上一页的版式语义和视觉重心形成变化。"
        selected.append(chosen)
    return selected


def _compatible(candidate: dict[str, Any], previous: dict[str, Any] | None) -> bool:
    if not previous: return True
    current_profile = get_layout_profile(candidate["value"])
    previous_profile = get_layout_profile(previous["value"])
    return candidate["value"] != previous["value"] and current_profile.semantic_group != previous_profile.semantic_group and current_profile.visual_axis != previous_profile.visual_axis
