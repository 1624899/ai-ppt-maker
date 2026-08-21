from __future__ import annotations

from typing import Any, Iterable, Sequence

from ppt_system.generation.design_grammar import DEFAULT_LAYOUT_FAMILIES, normalize_layout_family_name, validate_layout_family
from ppt_system.generation.layout_intent import infer_layout_intent
from ppt_system.generation.layout_profiles import LAYOUT_PROFILES, get_layout_profile


def recommend_layout_candidates(title: str, summary: str, bullets: Sequence[str], *, page_richness: str = "medium", candidate_families: Iterable[str] | None = None, page_index: int = 0, include_cover_page: bool = True, limit: int = 5) -> list[dict[str, Any]]:
    """基于页面意图生成可解释的版式候选，供编排器和前端共同使用。"""
    intent = infer_layout_intent(title, summary, bullets, page_richness=page_richness, page_index=page_index, include_cover_page=include_cover_page)
    candidates = _normalize_candidates(candidate_families)
    result: list[dict[str, Any]] = []
    for family in candidates:
        profile = get_layout_profile(family)
        score, reasons = _score_layout(profile, intent, f"{title} {summary} {' '.join(str(item) for item in bullets)}".lower())
        reasons.update({
            "layout_label": profile.label,
            "profile_description": profile.description,
            "suitable_for": list(profile.suitable_for),
            "avoid_for": list(profile.avoid_for),
            "semantic_group": profile.semantic_group,
        })
        result.append({"value": family, "score": score, "reason": reasons, "layout_intent": intent.to_dict()})
    return sorted(result, key=lambda item: (-item["score"], candidates.index(item["value"])))[:limit]


def recommend_layout_family(title: str, summary: str, bullets: Sequence[str], *, previous_family: str = "", **kwargs: object) -> str:
    candidates = recommend_layout_candidates(title, summary, bullets, **kwargs)
    previous = normalize_layout_family_name(previous_family) if previous_family else ""
    return next((item["value"] for item in candidates if item["value"] != previous), candidates[0]["value"] if candidates else "grid_n_x_m")


def choose_layout_family(suggested_family: str, title: str, summary: str, bullets: Sequence[str], **kwargs: object) -> str:
    previous_family = str(kwargs.pop("previous_family", ""))
    candidates = recommend_layout_candidates(title, summary, bullets, **kwargs)
    suggested = normalize_layout_family_name(suggested_family) if suggested_family else ""
    if not suggested or not any(item["value"] == suggested for item in candidates):
        return recommend_layout_family(title, summary, bullets, previous_family=previous_family, **kwargs)
    suggested_item = next(item for item in candidates if item["value"] == suggested)
    recommended = candidates[0] if candidates else suggested_item
    # 只要推荐候选在语义上更匹配，就纠正模型可能随意返回的版式。
    return recommended["value"] if recommended["score"] > suggested_item["score"] else suggested


def _score_layout(profile: Any, intent: Any, text: str) -> tuple[int, dict[str, Any]]:
    score = 0
    signals: list[str] = []
    if intent.intent in profile.intent_types:
        score += 36; signals.append(_intent_label(intent.intent))
    if intent.density in profile.density_levels:
        score += 16
    else:
        score -= 12
    if profile.min_items <= intent.item_count <= profile.max_items:
        score += 14
    else:
        score -= 10
    if intent.has_metrics and profile.supports_chart:
        score += 18; signals.append("关键指标")
    elif intent.has_metrics and not profile.supports_chart:
        score -= 8
    if intent.has_image_focus and profile.supports_image:
        score += 14; signals.append("主视觉对象")
    if intent.intent in {"cover", "key_message"} and profile.visual_strength == "high":
        score += 10
    # 在通用意图候选中优先推荐信息结构最直接的版式，其余同类版式作为替代方案。
    if intent.intent == "comparison" and profile.value == "compare_dual_axis":
        score += 34
    if intent.intent == "data_analysis" and profile.value in {"line_chart", "bar_chart", "dashboard"}:
        score += 8
    keyword_hits = [word for word in profile.keywords if word.lower() in text]
    score += min(len(keyword_hits), 3) * 12
    if profile.value in {"funnel", "gantt_chart", "swimlane", "dashboard", "line_chart", "bar_chart", "org_chart", "map_distribution"}:
        score += min(len(keyword_hits), 3) * 14
    signals.extend(keyword_hits[:3])
    if intent.intent == "comparison" and intent.comparison_object_count:
        content_fit = f"页面包含 {intent.comparison_object_count} 组对象和 {intent.dimension_count} 个比较维度，适合{profile.label}的对照结构。"
    elif intent.has_metrics:
        content_fit = f"页面包含 {intent.metric_count} 个数值信号和 {intent.item_count} 个要点，适合{profile.label}的数据承载能力。"
    else:
        content_fit = f"页面包含 {intent.item_count} 个要点，适合{profile.label}的内容容量。"
    density_fit = f"当前信息密度为{'高' if intent.density == 'high' else '中等' if intent.density == 'medium' else '较低'}，与该版式匹配。"
    return score, {"matched_intent": intent.intent, "matched_signals": signals or list(intent.matched_signals), "content_fit": content_fit, "density_fit": density_fit, "tradeoff": f"若内容超出 {profile.max_items} 个要点，建议选择更高密度的版式。"}


def _intent_label(intent: str) -> str:
    return {"cover": "开场主题", "comparison": "对比关系", "process": "步骤关系", "timeline": "时间顺序", "relationship": "结构关系", "data_analysis": "数据分析", "product_showcase": "主视觉对象", "summary": "总结结论", "action_plan": "行动安排", "key_message": "核心观点"}.get(intent, intent)


def _normalize_candidates(values: object) -> list[str]:
    source = values if isinstance(values, (list, tuple, set)) else DEFAULT_LAYOUT_FAMILIES
    result: list[str] = []
    for value in source:
        family = normalize_layout_family_name(str(value))
        if validate_layout_family(family) and family not in result:
            result.append(family)
    return result or list(DEFAULT_LAYOUT_FAMILIES)
