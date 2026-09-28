from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ppt_system.generation.page_richness import DEFAULT_PAGE_RICHNESS, normalize_page_richness_level


@dataclass(frozen=True)
class SourceContentBudget:
    """描述一页内容从事实锚点落字时可使用的内容预算。"""

    richness: str
    input_scale: str
    max_bullets: int
    summary_fact_count: int
    summary_max_chars: int
    allow_short_expansion: bool
    guidance: str


def resolve_source_content_budget(
    richness: Any = DEFAULT_PAGE_RICHNESS,
    *,
    fact_count: int = 0,
    source_char_count: int = 0,
) -> SourceContentBudget:
    """根据事实量和丰富度，决定本页应摘取、总结或轻量扩写到什么程度。"""

    normalized = normalize_page_richness_level(richness)
    input_scale = classify_source_content_scale(
        fact_count=fact_count,
        source_char_count=source_char_count,
    )
    base = _BASE_BUDGETS[normalized]
    budget = dict(base)

    if input_scale == "long":
        budget.update(_LONG_CONTENT_OVERRIDES[normalized])
        guidance = "长内容页：围绕所选事实锚点做重点突出和语义总结，不按原文逐条堆叠。"
    elif input_scale == "short":
        budget.update(_SHORT_CONTENT_OVERRIDES[normalized])
        guidance = "短内容页：只允许承接性轻量扩写和视觉支撑，不新增业务事实、数字或结论。"
    else:
        guidance = "适中内容页：保持事实完整，按页面丰富度控制要点数量和摘要长度。"

    max_bullets = int(budget["max_bullets"])
    if fact_count > 0:
        factual_limit = fact_count + 1 if bool(budget["allow_short_expansion"]) else fact_count
        max_bullets = min(max_bullets, factual_limit)
    max_bullets = max(1, max_bullets)

    summary_fact_count = max(1, min(int(budget["summary_fact_count"]), max_bullets))
    return SourceContentBudget(
        richness=normalized,
        input_scale=input_scale,
        max_bullets=max_bullets,
        summary_fact_count=summary_fact_count,
        summary_max_chars=int(budget["summary_max_chars"]),
        allow_short_expansion=bool(budget["allow_short_expansion"]),
        guidance=guidance,
    )


def classify_source_content_scale(*, fact_count: int = 0, source_char_count: int = 0) -> str:
    """粗分本页事实量，用于决定是压缩、正常呈现还是轻量补足。"""

    if fact_count <= 2 or source_char_count < 120:
        return "short"
    if fact_count >= 6 or source_char_count >= 180 or (fact_count >= 3 and source_char_count >= 150):
        return "long"
    return "balanced"


def count_anchor_facts(anchors: list[dict[str, Any]]) -> int:
    total = 0
    for anchor in anchors:
        facts = anchor.get("facts", [])
        if isinstance(facts, list):
            total += sum(1 for item in facts if str(item).strip())
    return total


def count_anchor_source_chars(anchors: list[dict[str, Any]]) -> int:
    return sum(len(str(anchor.get("source_text", "")).strip()) for anchor in anchors)


def build_source_content_control_prompt() -> str:
    """生成给规划模型看的内容把控规则。"""

    return "\n".join(
        [
            "- 页面内容以 source_anchor_ids 选中的事实锚点为基础，丰富度只决定取舍、总结深度和视觉承载密度。",
            "- 低丰富度：保留最关键事实，适合结论页、过渡页或信息较少的页面。",
            "- 中丰富度：保留 2 到 4 个核心事实，适合常规汇报页。",
            "- 高丰富度：可以承载更多事实和层次，但仍必须来自锚点，不能为了显得丰富而新增数字、事项、结论或口径。",
            "- 输入偏长时做重点突出和语义总结；输入偏短时只做少量承接性扩写，优先用版式、图形和留白降低紧凑感。",
            "- 如果输入完全没有层级或页规划，先根据事实锚点归纳主题和叙事线，再为每页选择 source_anchor_ids；不要机械均分，也不要把自拟页标题写回成事实。",
        ]
    )


_BASE_BUDGETS = {
    "low": {
        "max_bullets": 2,
        "summary_fact_count": 1,
        "summary_max_chars": 120,
        "allow_short_expansion": False,
    },
    "medium": {
        "max_bullets": 4,
        "summary_fact_count": 2,
        "summary_max_chars": 180,
        "allow_short_expansion": False,
    },
    "high": {
        "max_bullets": 6,
        "summary_fact_count": 3,
        "summary_max_chars": 240,
        "allow_short_expansion": False,
    },
}

_LONG_CONTENT_OVERRIDES = {
    "low": {"max_bullets": 2, "summary_fact_count": 1, "summary_max_chars": 110, "allow_short_expansion": False},
    "medium": {"max_bullets": 4, "summary_fact_count": 2, "summary_max_chars": 170, "allow_short_expansion": False},
    "high": {"max_bullets": 6, "summary_fact_count": 3, "summary_max_chars": 230, "allow_short_expansion": False},
}

_SHORT_CONTENT_OVERRIDES = {
    "low": {"max_bullets": 1, "summary_fact_count": 1, "summary_max_chars": 100, "allow_short_expansion": False},
    "medium": {"max_bullets": 2, "summary_fact_count": 1, "summary_max_chars": 140, "allow_short_expansion": True},
    "high": {"max_bullets": 3, "summary_fact_count": 1, "summary_max_chars": 170, "allow_short_expansion": True},
}
