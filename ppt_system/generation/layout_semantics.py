from __future__ import annotations

from ppt_system.generation.design_grammar import format_layout_family_for_prompt, validate_layout_family


def semantic_slots_for_family(layout_family: str) -> list[str]:
    """返回规划和提示词使用的中文语义分区。"""
    slots_by_family = {
        "grid_n_x_m": ["标题区", "卡片区1", "卡片区2", "卡片区3", "卡片区4"],
        "timeline_horizontal": ["标题区", "时间轴", "节点1", "节点2", "节点3"],
        "timeline_vertical": ["标题区", "时间轴", "节点1", "节点2", "节点3"],
        "process_horizontal": ["标题区", "步骤1", "步骤2", "步骤3"],
        "process_vertical": ["标题区", "步骤1", "步骤2", "步骤3"],
        "hub_and_spoke": ["中心主题", "分支1", "分支2", "分支3", "分支4"],
        "split_top_bottom": ["上方内容区", "下方内容区"],
        "compare_dual_axis": ["标题区", "左侧对比项", "右侧对比项", "对比维度"],
        "hero_with_supporting_cards": ["主视觉区", "辅助卡片1", "辅助卡片2", "辅助卡片3"],
        "floor_plan": ["顶部主题区", "区域1", "区域2", "区域3", "区域4", "区域5", "区域6", "底部支撑区"],
        "split_left_right": ["左侧内容区", "右侧内容区"],
    }
    if layout_family in slots_by_family:
        return slots_by_family[layout_family]
    if validate_layout_family(layout_family):
        return ["标题区", f"{format_layout_family_for_prompt(layout_family)}主体区"]
    return slots_by_family["split_left_right"]
