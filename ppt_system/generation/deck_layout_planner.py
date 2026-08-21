from __future__ import annotations

from typing import Any

from ppt_system.generation.layout_profiles import get_layout_profile


def plan_deck_layouts(page_candidates: list[list[dict[str, Any]]], *, locked_families: list[str | None] | None = None) -> list[dict[str, Any]]:
    """使用有限宽度 Beam Search 选择整套版式，而不是只看当前页面。"""
    if not page_candidates:
        return []
    locked_families = locked_families or []
    beams: list[tuple[float, list[dict[str, Any]]]] = [(0.0, [])]
    width = min(8, max(3, len(page_candidates)))
    for index, candidates in enumerate(page_candidates):
        next_beams: list[tuple[float, list[dict[str, Any]]]] = []
        locked = locked_families[index] if index < len(locked_families) else None
        for total_score, selected in beams:
            previous = selected[-1] if selected else None
            ranked = sorted(candidates, key=lambda item: item.get("score", 0), reverse=True)
            if locked:
                ranked = [item for item in ranked if item.get("value") == locked] or ranked
            for candidate in ranked[: max(width, 5)]:
                if previous and not _compatible(candidate, previous):
                    continue
                penalty = 0 if _deck_compatible(candidate, selected, len(page_candidates)) else 16
                next_beams.append((total_score + float(candidate.get("score", 0)) - penalty, selected + [candidate]))
        beams = sorted(next_beams, key=lambda item: item[0], reverse=True)[:width] or beams
    selected = max(beams, key=lambda item: item[0])[1]
    for index, chosen in enumerate(selected):
        if index:
            chosen.setdefault("reason", {})["deck_fit"] = "与整套 PPT 的语义组和视觉方向形成变化。"
    return selected


def build_deck_layout_report(selected: list[dict[str, Any]]) -> dict[str, Any]:
    """生成整套版式质量摘要，供前端或日志展示。"""
    if len(selected) < 2:
        return {
            "page_count": len(selected),
            "scope": "single_page",
            "enabled": False,
            "distinct_semantic_groups": 0,
            "distinct_visual_axes": 0,
            "diversity_score": None,
            "issues": [],
            "suggestions": [],
        }
    profiles = [get_layout_profile(item["value"]) for item in selected]
    groups = [item.semantic_group for item in profiles]
    axes = [item.visual_axis for item in profiles]
    issues: list[str] = []
    suggestions: list[str] = []
    for index in range(1, len(profiles)):
        if groups[index] == groups[index - 1]: issues.append(f"第 {index + 1} 页与上一页语义组重复")
        if axes[index] == axes[index - 1]: issues.append(f"第 {index + 1} 页与上一页视觉方向重复")
    target = 0 if len(selected) <= 3 else 3 if len(selected) <= 5 else 4 if len(selected) <= 7 else 5 if len(selected) <= 9 else 6
    distinct_groups = len(set(groups))
    if distinct_groups < target:
        issues.append(f"语义组覆盖不足，当前 {distinct_groups} 组，建议至少 {target} 组")
        suggestions.append("将部分重复的卡片或流程页替换为数据、对比、关系或场景版式。")
    if any(groups[index] == groups[index - 1] for index in range(1, len(groups))):
        suggestions.append("调整相邻页面的语义组，避免连续使用相似表达结构。")
    if any(axes[index] == axes[index - 1] for index in range(1, len(axes))):
        suggestions.append("在横向、纵向、网格、图表和视觉型构图之间增加切换。")
    diversity = round(min(100, (distinct_groups / max(1, target or 1)) * 55 + (len(set(axes)) / max(1, len(selected))) * 45))
    return {"page_count": len(selected), "scope": "multi_page", "enabled": True, "distinct_semantic_groups": distinct_groups, "distinct_visual_axes": len(set(axes)), "diversity_score": diversity, "issues": issues, "suggestions": suggestions}


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
