"""特殊版式的语义几何规则。"""
from __future__ import annotations

from ppt_system.generation.layout_blueprint_catalog import build_blueprint


HORIZONTAL_FAMILIES = {"progressive_relation", "road_map", "cycle_process", "relationship_chain", "milestones", "value_chain", "input_process_output", "three_part", "five_step", "route_planning", "annual_plan"}
VERTICAL_FAMILIES = {"pyramid_structure", "funnel", "staircase", "layered_structure", "checklist", "priority_ranking", "tower_structure", "growth_staircase", "iceberg_model"}
QUADRANT_FAMILIES = {"swot", "pros_cons", "comparison_table", "venn_relation", "problem_cause_solution", "goal_strategy_action", "case_breakdown", "retrospective"}
RADIAL_FAMILIES = {"circular_cycle", "ecosystem", "closed_loop_management", "fishbone"}
VISUAL_FAMILIES = {"floor_plan", "full_screen_visual", "map_distribution", "people_profile", "product_showcase", "scenario_showcase", "scenario_map", "visual_metaphor"}

CATEGORY_FAMILIES = {
    "流程": HORIZONTAL_FAMILIES | {"timeline_horizontal", "timeline_vertical", "process_horizontal", "process_vertical", "gantt_chart", "swimlane"},
    "关系": RADIAL_FAMILIES | {"hub_and_spoke", "org_chart", "venn_relation", "relationship_chain"},
    "分析": QUADRANT_FAMILIES | VERTICAL_FAMILIES,
    "视觉": VISUAL_FAMILIES | {"magazine_editorial", "collage", "achievement_wall"},
    "数据": {"data_cards", "big_number", "dashboard", "bar_chart", "line_chart", "pie_chart", "scatter_plot", "data_table"},
}


def build_layout_slot_specs(family: str, width: int, height: int, scale: float = 1.0) -> dict[str, dict]:
    specs: dict[str, dict] = {}
    content_index = 0
    for shape in build_layout_preview(family):
        if bool(shape.get("decorative")):
            continue
        if shape["kind"] == "title":
            name = "title"
        else:
            content_index += 1
            name = _slot_name(family, shape["kind"], content_index)
        box_height = shape["height"] if name == "title" else round(shape["height"] * scale)
        box = (
            round(shape["left"] / 1000 * width), round(shape["top"] / 562 * height),
            round(shape["width"] / 1000 * width), round(box_height / 562 * height),
        )
        specs[name] = {"box": box, "kind": shape["kind"], "label": shape.get("label", "")}
    return specs


def _slot_name(family: str, kind: str, index: int) -> str:
    if family == "split_left_right": return "left_text" if index == 1 else "right_visual"
    if family == "split_top_bottom": return "top_visual" if index == 1 else "bottom_text"
    if family == "grid_n_x_m": return f"cell_{index}"
    if family in {"process_horizontal", "process_vertical"}: return f"step_{index}"
    if family == "hub_and_spoke": return "hub_center" if kind == "circle-center" else f"spoke_{index}"
    if family == "hero_with_supporting_cards": return "hero_center" if index == 1 else f"card_{index - 1}"
    return f"content_{index}"


def get_layout_category(family: str) -> str:
    for category, families in CATEGORY_FAMILIES.items():
        if family in families:
            return category
    return "基础"


def build_layout_preview(family: str) -> list[dict]:
    """读取唯一蓝图，前端预览和实际排版不再维护两套结构。"""
    return build_blueprint(family)
