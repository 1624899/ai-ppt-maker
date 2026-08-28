from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from ppt_system.generation.generation_prompts import build_elements_prompt


def build_planned_runtime_pages(pages: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """把内容规划页面转换为运行态页面，并完整保留版式推荐信息。"""
    return [_build_planned_runtime_page(page) for page in pages]


def _build_planned_runtime_page(page: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "page_no": int(page["page_no"]),
        "title": page["title"],
        "summary": page.get("summary", ""),
        "bullets": copy.deepcopy(page.get("bullets", [])),
        "layout_intent": copy.deepcopy(page.get("layout_intent", "")),
        "layout_family": page.get("layout_family", ""),
        "layout_reason": page.get("layout_reason", ""),
        "layout_recommendation": copy.deepcopy(page.get("layout_recommendation", {})),
        "layout_candidates": copy.deepcopy(page.get("layout_candidates", [])),
        "layout_source": page.get("layout_source", "ai"),
        "layout_locked": bool(page.get("layout_locked")),
        "layout_user_confirmed": bool(page.get("layout_user_confirmed")),
        "page_richness": page.get("page_richness", ""),
        "visual_suggestion": page.get("visual_suggestion", ""),
        "style_constraints": page.get("style_constraints", ""),
        "source_anchor_ids": copy.deepcopy(page.get("source_anchor_ids", [])),
        "element_plan": copy.deepcopy(page.get("element_plan", {})),
        "chart_data": copy.deepcopy(page.get("chart_data")),
        "reference_mode": page.get("reference_mode", "generation"),
        "prompt_profile": page.get("prompt_profile", "compressed"),
        "evaluation": copy.deepcopy(page.get("evaluation", {})),
        "status": "planned",
        "reference_image": "",
        "element_image": "",
        "reference_prompt": page.get("image_prompt", ""),
        "elements_prompt": build_elements_prompt(),
        "layout_slots": copy.deepcopy(page.get("layout_slots", [])),
        "texts": copy.deepcopy(page.get("texts", [])),
    }
