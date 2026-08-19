from __future__ import annotations

import re
from ppt_system.generation.layout_geometry import build_layout_slot_specs
from typing import Any
from ppt_system.generation.planner import estimate_page_count

try:
    from ppt_system.generation.design_grammar import ALLOWED_LAYOUT_FAMILIES, validate_layout_family
except Exception:
    ALLOWED_LAYOUT_FAMILIES = [
        "split_left_right", "split_top_bottom",
        "timeline_horizontal", "timeline_vertical",
        "hub_and_spoke", "grid_n_x_m", "compare_dual_axis",
        "process_horizontal", "process_vertical",
        "hero_with_supporting_cards",
    ]

    def validate_layout_family(name: str) -> bool:
        return name in ALLOWED_LAYOUT_FAMILIES

_SLOT_TEMPLATES: dict[str, dict] = {
    "split_left_right": {
        "title": {"anchor": "top_left"},
        "content_blocks": ["left_text", "right_visual"],
        "visual_focus": "right_center",
    },
    "split_top_bottom": {
        "title": {"anchor": "top_center"},
        "content_blocks": ["top_visual", "bottom_text"],
        "visual_focus": "center",
    },
    "compare_dual_axis": {
        "title": {"anchor": "top_center"},
        "content_blocks": ["left_compare", "right_compare", "axis_notes"],
        "visual_focus": "center",
    },
    "timeline_horizontal": {
        "title": {"anchor": "top_left"},
        "content_blocks": ["timeline_items_left_to_right"],
        "visual_focus": "center_horizontal",
    },
    "timeline_vertical": {
        "title": {"anchor": "top_center"},
        "content_blocks": ["timeline_items_top_to_bottom"],
        "visual_focus": "center_vertical",
    },
    "hub_and_spoke": {
        "title": {"anchor": "center"},
        "content_blocks": ["spoke_1", "spoke_2", "spoke_3", "spoke_4"],
        "visual_focus": "center",
    },
    "grid_n_x_m": {
        "title": {"anchor": "top_left"},
        "content_blocks": ["cell_1", "cell_2", "cell_3", "cell_4"],
        "visual_focus": "grid_center",
    },
    "process_horizontal": {
        "title": {"anchor": "top_left"},
        "content_blocks": ["step_1", "step_2", "step_3"],
        "visual_focus": "center_horizontal",
    },
    "process_vertical": {
        "title": {"anchor": "top_center"},
        "content_blocks": ["step_1", "step_2", "step_3"],
        "visual_focus": "center_vertical",
    },
    "hero_with_supporting_cards": {
        "title": {"anchor": "center_top"},
        "content_blocks": ["hero_center", "card_1", "card_2", "card_3"],
        "visual_focus": "center",
    },
}

_DENSITY_SCALE: dict[str, float] = {"low": 0.85, "medium": 1.0, "high": 1.15}

# 新增版式采用统一的语义槽位骨架，具体视觉由页面生图提示和元素层继续细化。
_SPECIAL_LAYOUT_BLOCKS = {
    "floor_plan": ["rooms"], "magazine_editorial": ["lead_visual", "article_text", "sidebar"], "full_screen_visual": ["hero_visual"],
    "circular_cycle": ["cycle_items"], "pyramid_structure": ["levels"], "funnel": ["funnel_stages"], "staircase": ["steps"], "progressive_relation": ["relations"], "road_map": ["route_nodes"], "gantt_chart": ["schedule"], "cycle_process": ["cycle_steps"], "swimlane": ["lanes"], "org_chart": ["hierarchy"], "relationship_chain": ["chain_nodes"], "venn_relation": ["set_a", "intersection", "set_b"],
    "data_cards": ["metric_cards"], "big_number": ["headline_metric", "supporting_metrics"], "dashboard": ["dashboard_panels"], "bar_chart": ["bars"], "line_chart": ["trend_line"], "pie_chart": ["slices"], "scatter_plot": ["points"], "data_table": ["table"], "map_distribution": ["map", "legend"],
    "people_profile": ["portrait", "profile_text"], "product_showcase": ["product_visual", "features"], "case_breakdown": ["context", "approach", "result"], "problem_cause_solution": ["problem", "cause", "solution"], "goal_strategy_action": ["goal", "strategy", "action"], "summary_detail": ["summary", "details"], "layered_structure": ["layers"], "module_combination": ["modules"], "collage": ["collage_items"], "tag_categories": ["tag_groups"], "checklist": ["items"], "milestones": ["milestone_items"], "priority_ranking": ["ranked_items"], "value_chain": ["value_links"], "ecosystem": ["ecosystem_nodes"], "closed_loop_management": ["loop_stages"], "input_process_output": ["input", "process", "output"], "three_part": ["part_1", "part_2", "part_3"], "five_step": ["step_1", "step_2", "step_3", "step_4", "step_5"], "comparison_table": ["comparison_rows"], "pros_cons": ["pros", "cons"], "swot": ["strengths", "weaknesses", "opportunities", "threats"], "fishbone": ["causes", "effect"], "iceberg_model": ["visible", "hidden"], "tower_structure": ["tower_levels"], "growth_staircase": ["growth_steps"], "route_planning": ["route_stages"], "annual_plan": ["quarters"], "retrospective": ["achievements", "lessons", "next_steps"], "achievement_wall": ["achievement_cards"], "scenario_showcase": ["scenes"], "scenario_map": ["map_zones"], "infographic": ["visual_facts"], "visual_metaphor": ["metaphor_visual", "explanation"],
}
for _family, _blocks in _SPECIAL_LAYOUT_BLOCKS.items():
    _SLOT_TEMPLATES.setdefault(_family, {"title": {"anchor": "top_left"}, "content_blocks": _blocks, "visual_focus": "center"})


def list_supported_layout_slot_families() -> set[str]:
    return set(_SLOT_TEMPLATES)


def split_sentences(content: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?])\s*|\n+", content)
    return [part.strip() for part in parts if part.strip()]


def chunk_sentences(sentences: list[str], page_count: int) -> list[list[str]]:
    if not sentences:
        return [[] for _ in range(page_count)]

    chunks: list[list[str]] = []
    base = max(1, round(len(sentences) / page_count))
    cursor = 0
    for page_index in range(page_count):
        remaining_pages = page_count - page_index
        remaining_sentences = len(sentences) - cursor
        take = max(1, round(remaining_sentences / remaining_pages))
        take = min(max(take, base - 1), base + 1, remaining_sentences)
        chunks.append(sentences[cursor : cursor + take])
        cursor += take

    if cursor < len(sentences):
        chunks[-1].extend(sentences[cursor:])
    return chunks


def make_title(sentence: str, fallback: str) -> str:
    sentence = re.sub(r"[。！？!?，,；;：:]\s*$", "", sentence.strip())
    if not sentence:
        return fallback
    if len(sentence) <= 18:
        return sentence
    return sentence[:18].rstrip() + "..."


def build_layout_slots_by_family(
    layout_family: str,
    image_width: int,
    image_height: int,
    content_density: str = "medium",
) -> dict:
    family = layout_family if layout_family in _SLOT_TEMPLATES else "split_left_right"
    template = _SLOT_TEMPLATES[family]
    scale = _DENSITY_SCALE.get(content_density, 1.0)
    slot_specs = build_layout_slot_specs(family, image_width, image_height, scale)
    slot_coords = {name: tuple(spec["box"]) for name, spec in slot_specs.items()}

    return {
        "family": family,
        "template": template,
        "slot_coords": slot_coords,
        "slot_kinds": {name: spec["kind"] for name, spec in slot_specs.items()},
    }


def build_text_boxes_from_slots(
    slots: dict,
    title: str,
    body: str,
    image_width: int,
    image_height: int,
) -> list[dict]:
    family = slots.get("family", "split_left_right")
    coords = slots.get("slot_coords", {})
    coords = {
        name: tuple(int(round(float(value))) for value in box)
        for name, box in coords.items()
        if isinstance(box, (list, tuple)) and len(box) == 4
    }
    slot_kinds = slots.get("slot_kinds", {})
    body_lines = [line for line in body.split("\n") if line.strip()]

    boxes: list[dict] = []

    if "title" in coords:
        l, t, w, h = coords["title"]
        boxes.append({
            "role": "title", "text": title,
            "left": l, "top": t, "width": w, "height": h,
            "font_size": 34, "bold": True, "color": "FFFFFF",
        })

    content_blocks = [name for name in coords if name != "title"]
    text_block_indices: list[int] = []
    visual_kinds = {"visual", "portrait", "product", "map", "pie", "chart-panel"}
    for i, block_name in enumerate(content_blocks):
        if block_name in coords:
            l, t, w, h = coords[block_name]
            is_visual = slot_kinds.get(block_name) in visual_kinds
            if is_visual:
                boxes.append({
                    "role": "slot", "text": "",
                    "left": l, "top": t, "width": w, "height": h,
                    "font_size": 0, "bold": False, "color": "000000",
                })
            else:
                text_block_indices.append(i)

    text_content_parts = list(body_lines)
    for idx_pos, block_idx in enumerate(text_block_indices):
        block_name = content_blocks[block_idx]
        if block_name not in coords:
            continue
        l, t, w, h = coords[block_name]
        if len(text_block_indices) > 1:
            chunk_size = max(1, len(text_content_parts) // len(text_block_indices))
            start = idx_pos * chunk_size
            end = start + chunk_size if idx_pos < len(text_block_indices) - 1 else len(text_content_parts)
            text = "\n".join(text_content_parts[start:end])
        else:
            text = "\n".join(text_content_parts)
        boxes.append({
            "role": "body", "text": text,
            "left": l, "top": t, "width": w, "height": h,
            "font_size": 22, "bold": False, "color": "DDEBFF",
        })

    if len(boxes) <= 1:
        l = round(image_width * 0.06)
        t = round(image_height * 0.26)
        w = round(image_width * 0.42)
        h = round(image_height * 0.48)
        boxes.append({
            "role": "body", "text": body,
            "left": l, "top": t, "width": w, "height": h,
            "font_size": 22, "bold": False, "color": "DDEBFF",
        })

    return boxes


def build_fallback_boxes_for_family(
    layout_family: str,
    title: str,
    body: str,
    image_width: int,
    image_height: int,
) -> list[dict]:
    W, H = image_width, image_height
    family = layout_family if layout_family in _SLOT_TEMPLATES else "split_left_right"

    if family == "split_left_right":
        return [
            {"role": "title", "text": title, "left": round(W * 0.06), "top": round(H * 0.12), "width": round(W * 0.42), "height": round(H * 0.10), "font_size": 34, "bold": True, "color": "FFFFFF"},
            {"role": "body", "text": body, "left": round(W * 0.06), "top": round(H * 0.26), "width": round(W * 0.42), "height": round(H * 0.48), "font_size": 22, "bold": False, "color": "DDEBFF"},
        ]
    if family == "split_top_bottom":
        return [
            {"role": "title", "text": title, "left": round(W * 0.06), "top": round(H * 0.04), "width": round(W * 0.88), "height": round(H * 0.10), "font_size": 34, "bold": True, "color": "FFFFFF"},
            {"role": "body", "text": body, "left": round(W * 0.06), "top": round(H * 0.58), "width": round(W * 0.88), "height": round(H * 0.32), "font_size": 22, "bold": False, "color": "DDEBFF"},
        ]
    if family == "compare_dual_axis":
        left_body, right_body, axis_body = split_body_for_blocks(body, 3)
        return [
            {"role": "title", "text": title, "left": round(W * 0.06), "top": round(H * 0.05), "width": round(W * 0.88), "height": round(H * 0.10), "font_size": 34, "bold": True, "color": "FFFFFF"},
            {"role": "body", "text": left_body, "left": round(W * 0.06), "top": round(H * 0.22), "width": round(W * 0.36), "height": round(H * 0.56), "font_size": 22, "bold": False, "color": "DDEBFF"},
            {"role": "body", "text": right_body, "left": round(W * 0.58), "top": round(H * 0.22), "width": round(W * 0.36), "height": round(H * 0.56), "font_size": 22, "bold": False, "color": "DDEBFF"},
            {"role": "body", "text": axis_body, "left": round(W * 0.43), "top": round(H * 0.30), "width": round(W * 0.14), "height": round(H * 0.40), "font_size": 18, "bold": False, "color": "DDEBFF"},
        ]
    if family == "timeline_horizontal":
        return [
            {"role": "title", "text": title, "left": round(W * 0.06), "top": round(H * 0.06), "width": round(W * 0.40), "height": round(H * 0.10), "font_size": 34, "bold": True, "color": "FFFFFF"},
            {"role": "body", "text": body, "left": round(W * 0.06), "top": round(H * 0.22), "width": round(W * 0.88), "height": round(H * 0.55), "font_size": 22, "bold": False, "color": "DDEBFF"},
        ]
    if family == "timeline_vertical":
        return [
            {"role": "title", "text": title, "left": round(W * 0.06), "top": round(H * 0.04), "width": round(W * 0.88), "height": round(H * 0.10), "font_size": 34, "bold": True, "color": "FFFFFF"},
            {"role": "body", "text": body, "left": round(W * 0.06), "top": round(H * 0.18), "width": round(W * 0.88), "height": round(H * 0.65), "font_size": 22, "bold": False, "color": "DDEBFF"},
        ]
    if family == "hub_and_spoke":
        return [
            {"role": "title", "text": title, "left": round(W * 0.30), "top": round(H * 0.04), "width": round(W * 0.40), "height": round(H * 0.10), "font_size": 34, "bold": True, "color": "FFFFFF"},
            {"role": "body", "text": body, "left": round(W * 0.30), "top": round(H * 0.40), "width": round(W * 0.40), "height": round(H * 0.40), "font_size": 22, "bold": False, "color": "DDEBFF"},
        ]
    if family == "grid_n_x_m":
        return [
            {"role": "title", "text": title, "left": round(W * 0.06), "top": round(H * 0.04), "width": round(W * 0.40), "height": round(H * 0.10), "font_size": 34, "bold": True, "color": "FFFFFF"},
            {"role": "body", "text": body, "left": round(W * 0.06), "top": round(H * 0.18), "width": round(W * 0.88), "height": round(H * 0.72), "font_size": 22, "bold": False, "color": "DDEBFF"},
        ]
    if family == "process_horizontal":
        return [
            {"role": "title", "text": title, "left": round(W * 0.06), "top": round(H * 0.06), "width": round(W * 0.40), "height": round(H * 0.10), "font_size": 34, "bold": True, "color": "FFFFFF"},
            {"role": "body", "text": body, "left": round(W * 0.04), "top": round(H * 0.24), "width": round(W * 0.92), "height": round(H * 0.50), "font_size": 22, "bold": False, "color": "DDEBFF"},
        ]
    if family == "process_vertical":
        return [
            {"role": "title", "text": title, "left": round(W * 0.06), "top": round(H * 0.04), "width": round(W * 0.88), "height": round(H * 0.10), "font_size": 34, "bold": True, "color": "FFFFFF"},
            {"role": "body", "text": body, "left": round(W * 0.06), "top": round(H * 0.18), "width": round(W * 0.88), "height": round(H * 0.65), "font_size": 22, "bold": False, "color": "DDEBFF"},
        ]
    if family == "hero_with_supporting_cards":
        return [
            {"role": "title", "text": title, "left": round(W * 0.20), "top": round(H * 0.04), "width": round(W * 0.60), "height": round(H * 0.10), "font_size": 34, "bold": True, "color": "FFFFFF"},
            {"role": "body", "text": body, "left": round(W * 0.15), "top": round(H * 0.18), "width": round(W * 0.70), "height": round(H * 0.72), "font_size": 22, "bold": False, "color": "DDEBFF"},
        ]

    return [
        {"role": "title", "text": title, "left": round(W * 0.06), "top": round(H * 0.12), "width": round(W * 0.42), "height": round(H * 0.10), "font_size": 34, "bold": True, "color": "FFFFFF"},
        {"role": "body", "text": body, "left": round(W * 0.06), "top": round(H * 0.26), "width": round(W * 0.42), "height": round(H * 0.48), "font_size": 22, "bold": False, "color": "DDEBFF"},
    ]


def split_body_for_blocks(body: str, block_count: int) -> list[str]:
    count = max(1, block_count)
    lines = [line for line in body.split("\n") if line.strip()]
    if not lines:
        return [body] + [""] * (count - 1)
    chunk_size = max(1, (len(lines) + count - 1) // count)
    chunks = ["\n".join(lines[index : index + chunk_size]) for index in range(0, len(lines), chunk_size)]
    return (chunks + [""] * count)[:count]


def build_text_layouts(
    content: str,
    page_count: int | None = None,
    image_width: int = 2000,
    image_height: int = 1125,
    layout_families: list[str] | None = None,
) -> list[dict[str, Any]]:
    if page_count is None:
        page_count = estimate_page_count(content)

    sentences = split_sentences(content)
    chunks = chunk_sentences(sentences, page_count)

    default_families = [
        "split_left_right", "split_top_bottom",
        "timeline_horizontal", "process_horizontal",
        "hub_and_spoke", "grid_n_x_m",
    ]
    if layout_families is None:
        layout_families = [default_families[i % len(default_families)] for i in range(page_count)]

    pages: list[dict[str, Any]] = []

    for index, chunk in enumerate(chunks, start=1):
        title = make_title(chunk[0] if chunk else "", f"第 {index} 页")
        body_sentences = chunk[1:] if len(chunk) > 1 else chunk
        body = "\n".join(f"• {item}" for item in body_sentences[:5])

        family_idx = (index - 1) % len(layout_families)
        family = layout_families[family_idx]
        if not validate_layout_family(family):
            family = "split_left_right"

        slots = build_layout_slots_by_family(family, image_width, image_height)
        texts = build_text_boxes_from_slots(slots, title, body, image_width, image_height)

        if not texts or len(texts) <= 1:
            texts = build_fallback_boxes_for_family(family, title, body, image_width, image_height)

        pages.append(
            {
                "page_no": index,
                "title": title,
                "summary": " ".join(chunk),
                "texts": texts,
                "layout_family": family,
            }
        )

    return pages
