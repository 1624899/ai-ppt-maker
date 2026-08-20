from __future__ import annotations

from typing import Any

from ppt_system.generation.layout_profiles import get_layout_profile


def plan_deck_layouts(page_candidates: list[list[dict[str, Any]]], *, locked_families: list[str | None] | None = None) -> list[dict[str, Any]]:
    """按页面顺序选择候选，兼顾相邻页面和整套 PPT 的结构多样性。"""
    selected: list[dict[str, Any]] = []
    locked_families = locked_families or []
    for index, candidates in enumerate(page_candidates):
        locked = locked_families[index] if index < len(locked_families) else None
        ranked = sorted(candidates, key=lambda item: item.get("score", 0), reverse=True)
        if locked:
            ranked.sort(key=lambda item: item.get("value") != locked)
        previous = selected[-1] if selected else None
        chosen = next((item for item in ranked if _compatible(item, previous) and _deck_compatible(item, selected, len(page_candidates))), None)
        chosen = chosen or next((item for item in ranked if _compatible(item, previous)), ranked[0] if ranked else {})
        if previous and chosen:
            reason = chosen.setdefault("reason", {})
            reason["deck_fit"] = "与上一页的版式语义和视觉重心形成变化。"
        selected.append(chosen)
    return selected


def build_deck_layout_report(selected: list[dict[str, Any]]) -> dict[str, Any]:
    """生成整套版式质量摘要，供前端或日志展示。"""
    if not selected:
        return {"page_count": 0, "distinct_semantic_groups": 0, "distinct_visual_axes": 0, "diversity_score": 0, "issues": []}
    profiles = [get_layout_profile(item["value"]) for item in selected]
    groups = [item.semantic_group for item in profiles]
    axes = [item.visual_axis for item in profiles]
    issues: list[str] = []
    for index in range(1, len(profiles)):
        if groups[index] == groups[index - 1]: issues.append(f"第 {index + 1} 页与上一页语义组重复")
        if axes[index] == axes[index - 1]: issues.append(f"第 {index + 1} 页与上一页视觉方向重复")
    target = 0 if len(selected) <= 3 else 3 if len(selected) <= 5 else 4 if len(selected) <= 7 else 5 if len(selected) <= 9 else 6
    distinct_groups = len(set(groups))
    if distinct_groups < target: issues.append(f"语义组覆盖不足，当前 {distinct_groups} 组，建议至少 {target} 组")
    diversity = round(min(100, (distinct_groups / max(1, target or 1)) * 55 + (len(set(axes)) / max(1, len(selected))) * 45))
    return {"page_count": len(selected), "distinct_semantic_groups": distinct_groups, "distinct_visual_axes": len(set(axes)), "diversity_score": diversity, "issues": issues}


def _deck_compatible(candidate: dict[str, Any], selected: list[dict[str, Any]], total: int) -> bool:
    if not selected:
        return True
    profile = get_layout_profile(candidate["value"])
    groups = {get_layout_profile(item["value"]).semantic_group for item in selected}
    # 长文档优先扩大语义组覆盖；同组超过两次后仅在没有替代候选时允许使用。
    if profile.semantic_group in groups and len(selected) < min(total, 10) and sum(
        get_layout_profile(item["value"]).semantic_group == profile.semantic_group for item in selected
    ) >= 2:
        return False
    # 卡片与全屏视觉控制比例，封面由调用方锁定时仍可使用。
    if profile.semantic_group == "modules" and sum(get_layout_profile(item["value"]).semantic_group == "modules" for item in selected) >= max(2, total // 3):
        return False
    if profile.visual_strength == "high" and profile.semantic_group == "opening" and sum(get_layout_profile(item["value"]).semantic_group == "opening" for item in selected) >= max(1, total // 5):
        return False
    return True


def _compatible(candidate: dict[str, Any], previous: dict[str, Any] | None) -> bool:
    if not previous: return True
    current_profile = get_layout_profile(candidate["value"])
    previous_profile = get_layout_profile(previous["value"])
    return candidate["value"] != previous["value"] and current_profile.semantic_group != previous_profile.semantic_group and current_profile.visual_axis != previous_profile.visual_axis
