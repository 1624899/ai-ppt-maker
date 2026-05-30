from __future__ import annotations

from typing import Any, Mapping


PAGE_RICHNESS_LEVELS = ("low", "medium", "high")
DEFAULT_PAGE_RICHNESS = "medium"

_PAGE_RICHNESS_LABELS = {
    "low": "低",
    "medium": "中",
    "high": "高",
}

_PAGE_RICHNESS_PLANNING_GUIDANCE = {
    "low": "信息密度偏低，控制模块数量，突出 1 个核心观点与少量辅助信息，优先保证留白和视觉聚焦。",
    "medium": "信息密度适中，保持主次分明，通常包含 2 到 4 个信息模块，兼顾表达完整度与清晰度。",
    "high": "信息密度偏高，在保证层级清晰的前提下容纳更多信息模块、对比关系或流程节点，但不要堆叠到难以阅读。",
}

_PAGE_RICHNESS_RENDER_GUIDANCE = {
    "low": "控制视觉元素与文字块数量，优先放大主结论、主图形或核心对比，避免页面显得拥挤。",
    "medium": "保持均衡的信息密度，模块数量适中，兼顾留白、结构感和内容完整度。",
    "high": "允许出现更多卡片、节点、图表分区或说明标签，但必须维持清晰网格、明确分组和可读性。",
}


def normalize_page_richness_level(value: Any, default: str = DEFAULT_PAGE_RICHNESS) -> str:
    normalized_default = _coerce_supported_level(default) or DEFAULT_PAGE_RICHNESS
    normalized = _coerce_supported_level(value)
    return normalized or normalized_default


def normalize_page_richness_map(
    raw_value: Any,
    *,
    page_count: int,
    default_level: str = DEFAULT_PAGE_RICHNESS,
) -> dict[str, str]:
    normalized_default = normalize_page_richness_level(default_level)
    result: dict[str, str] = {}
    if page_count <= 0:
        return result

    if isinstance(raw_value, Mapping):
        iterator = raw_value.items()
    elif isinstance(raw_value, list):
        iterator = enumerate(raw_value, start=1)
    else:
        iterator = []

    for raw_page_no, raw_level in iterator:
        page_no = _normalize_page_no(raw_page_no)
        if page_no is None or page_no < 1 or page_no > page_count:
            continue
        result[str(page_no)] = normalize_page_richness_level(raw_level, normalized_default)
    return result


def resolve_page_richness_map(
    *,
    page_count: int,
    default_level: str = DEFAULT_PAGE_RICHNESS,
    explicit_map: Any = None,
) -> dict[str, str]:
    normalized_default = normalize_page_richness_level(default_level)
    explicit = normalize_page_richness_map(
        explicit_map,
        page_count=page_count,
        default_level=normalized_default,
    )
    return {
        str(page_no): explicit.get(str(page_no), normalized_default)
        for page_no in range(1, max(0, page_count) + 1)
    }


def describe_page_richness(level: Any) -> str:
    normalized = normalize_page_richness_level(level)
    return _PAGE_RICHNESS_LABELS.get(normalized, _PAGE_RICHNESS_LABELS[DEFAULT_PAGE_RICHNESS])


def build_page_richness_planning_guidance(level: Any) -> str:
    normalized = normalize_page_richness_level(level)
    return _PAGE_RICHNESS_PLANNING_GUIDANCE[normalized]


def build_page_richness_render_guidance(level: Any) -> str:
    normalized = normalize_page_richness_level(level)
    return _PAGE_RICHNESS_RENDER_GUIDANCE[normalized]


def build_page_richness_prompt_lines(page_richness_map: Mapping[str, Any]) -> list[str]:
    if not page_richness_map:
        return []
    lines: list[str] = []
    for page_no in sorted(page_richness_map.keys(), key=lambda value: int(value)):
        level = normalize_page_richness_level(page_richness_map.get(page_no))
        lines.append(
            f"- 第 {int(page_no)} 页：丰富度{describe_page_richness(level)}（{build_page_richness_planning_guidance(level)}）"
        )
    return lines


def _coerce_supported_level(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in PAGE_RICHNESS_LEVELS:
        return normalized
    return None


def _normalize_page_no(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
