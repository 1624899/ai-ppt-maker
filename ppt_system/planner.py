from __future__ import annotations

import math
import re
from typing import Any

try:
    from ppt_system.design_grammar import (
        ALLOWED_LAYOUT_FAMILIES,
        validate_layout_family,
        normalize_layout_family_name as _dg_normalize,
    )
except Exception:
    ALLOWED_LAYOUT_FAMILIES = [
        "split_left_right", "split_top_bottom",
        "timeline_horizontal", "timeline_vertical",
        "hub_and_spoke", "grid_n_x_m",
        "process_horizontal", "process_vertical",
        "hero_with_supporting_cards",
    ]

    def validate_layout_family(name: str) -> bool:
        return name in ALLOWED_LAYOUT_FAMILIES

    def _dg_normalize(name: str) -> str | None:
        return None

_DEFAULT_FAMILIES = [
    "split_left_right", "split_top_bottom",
    "timeline_horizontal", "timeline_vertical",
    "hub_and_spoke", "grid_n_x_m",
    "process_horizontal", "process_vertical",
    "hero_with_supporting_cards",
]

_CONTENT_TYPE_FAMILIES: dict[str, list[str]] = {
    "process": ["process_horizontal", "process_vertical", "timeline_horizontal"],
    "compare": ["split_left_right", "split_top_bottom"],
    "overview": ["hub_and_spoke", "grid_n_x_m", "hero_with_supporting_cards"],
    "timeline": ["timeline_horizontal", "timeline_vertical"],
}


def normalize_layout_family_name(name: str) -> str:
    result = _dg_normalize(name)
    if result and validate_layout_family(result):
        return result
    cleaned = name.strip().lower().replace("-", "_").replace(" ", "_")
    if validate_layout_family(cleaned):
        return cleaned
    return "split_left_right"


def infer_style_type(content: str, image_count: int = 0) -> str:
    text = content.lower()
    if any(word in text for word in ("战略", "增长", "市场", "商业", "roi", "营收")):
        return "商务汇报"
    if any(word in text for word in ("技术", "架构", "算法", "系统", "数据", "模型")):
        return "科技蓝图"
    if image_count >= 3:
        return "视觉展示"
    return "通用简报"


def estimate_page_count(content: str, min_pages: int = 3, max_pages: int = 12) -> int:
    paragraphs = [item for item in re.split(r"\n\s*\n|[。！？]\s*", content) if item.strip()]
    by_paragraphs = max(min_pages, math.ceil(len(paragraphs) / 2))
    by_chars = max(min_pages, math.ceil(len(content) / 420))
    return min(max(by_paragraphs, by_chars), max_pages)


def _detect_content_type(page_content: str) -> str:
    text = page_content.lower()
    if any(w in text for w in ("流程", "步骤", "阶段", "过程", "环节")):
        return "process"
    if any(w in text for w in ("对比", "比较", "vs", "差异", "优劣")):
        return "compare"
    if any(w in text for w in ("时间", "年", "月", "季度", "历史", "发展")):
        return "timeline"
    return "overview"


def infer_layout_family(
    content_type: str,
    page_index: int,
    total_pages: int,
    previous_families: list[str],
) -> str:
    if page_index == 0:
        return "hero_with_supporting_cards"
    if page_index == total_pages - 1:
        candidates = ["grid_n_x_m", "hub_and_spoke"]
        for fam in candidates:
            if fam not in previous_families[-1:]:
                return fam
        return candidates[0]
    candidates = _CONTENT_TYPE_FAMILIES.get(content_type, _CONTENT_TYPE_FAMILIES["overview"])
    for fam in candidates:
        if fam not in previous_families[-1:]:
            return fam
    return candidates[0]


def dedupe_layout_sequence(families: list[str]) -> list[str]:
    if not families:
        return families
    result = [families[0]]
    for fam in families[1:]:
        if fam == result[-1]:
            for alt in _DEFAULT_FAMILIES:
                if alt != fam:
                    result.append(alt)
                    break
            else:
                result.append(fam)
        else:
            result.append(fam)
    return result


def build_default_element_plan(style_guide: dict, page_content: str) -> dict:
    return {
        "primitives": style_guide.get("element_primitives", []),
        "icon_topics": [],
        "diagram_type": "default",
    }


def infer_reference_mode(
    page_index: int,
    total_pages: int,
    has_reference_images: bool,
    include_cover_page: bool = True,
) -> str:
    if not has_reference_images:
        return "generation"
    if include_cover_page and page_index == 0:
        return "edit_with_refs"
    if page_index == total_pages - 1 and total_pages > 2:
        return "edit_with_refs"
    return "generation"


def build_plan(content: str, image_count: int = 0) -> dict[str, Any]:
    page_count = estimate_page_count(content)
    return {
        "style_type": infer_style_type(content, image_count=image_count),
        "page_count": page_count,
        "image_generation_notes": [
            "生成多页 PPT 样式图时，要求无文字或文字区域留空。",
            "视觉元素低透明、边界清晰、元素之间留透明间隔，便于后续连通域分割。",
            "每页单独输出 PNG，尺寸保持一致，推荐 2000x1125 或 3840x2160。",
        ],
    }
