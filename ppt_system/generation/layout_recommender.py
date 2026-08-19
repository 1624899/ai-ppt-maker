from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from ppt_system.generation.design_grammar import DEFAULT_LAYOUT_FAMILIES, normalize_layout_family_name, validate_layout_family
from ppt_system.generation.page_richness import normalize_page_richness_level


@dataclass(frozen=True)
class LayoutProfile:
    keywords: tuple[str, ...]
    densities: tuple[str, ...] = ("low", "medium", "high")
    min_items: int = 0
    max_items: int = 99


# 版式语义集中维护，新增版式时只需扩展画像，无需修改选择流程。
LAYOUT_PROFILES: dict[str, LayoutProfile] = {
    "timeline_horizontal": LayoutProfile(("时间线", "时间轴", "历程", "演变", "发展", "沿革"), ("low", "medium"), 2, 6),
    "timeline_vertical": LayoutProfile(("时间线", "时间轴", "大事记", "历史", "事件", "阶段"), ("medium", "high"), 4),
    "process_horizontal": LayoutProfile(("流程", "步骤", "执行", "落地", "操作", "环节"), ("low", "medium"), 2, 5),
    "process_vertical": LayoutProfile(("流程", "步骤", "审批", "纵向", "分阶段"), ("medium", "high"), 4),
    "compare_dual_axis": LayoutProfile(("对比", "比较", "差异", "竞品", "方案对照", "之前", "之后"), min_items=2, max_items=6),
    "comparison_table": LayoutProfile(("对照表", "多维对比", "参数对比", "功能对比", "横向比较"), ("medium", "high"), 3),
    "pros_cons": LayoutProfile(("优劣势", "优点", "缺点", "利弊", "优势", "劣势"), min_items=2),
    "swot": LayoutProfile(("swot", "优势", "劣势", "机会", "威胁"), ("medium", "high"), 4, 8),
    "hub_and_spoke": LayoutProfile(("中心", "核心", "辐射", "分支", "围绕", "体系"), min_items=3, max_items=6),
    "ecosystem": LayoutProfile(("生态", "生态圈", "参与方", "伙伴", "协同网络", "利益相关方"), ("medium", "high"), 4),
    "relationship_chain": LayoutProfile(("关系链", "链路", "依赖", "关联", "传导", "上下游"), min_items=3),
    "venn_relation": LayoutProfile(("交集", "重叠", "共同", "集合", "兼具", "venn"), min_items=2, max_items=4),
    "org_chart": LayoutProfile(("组织架构", "组织结构", "部门", "岗位", "汇报关系", "团队结构"), ("medium", "high"), 3),
    "layered_structure": LayoutProfile(("分层", "层级", "架构层", "底层", "中层", "上层"), min_items=3),
    "pyramid_structure": LayoutProfile(("金字塔", "顶层", "基础层", "战略层", "递减", "层层支撑"), min_items=3),
    "tower_structure": LayoutProfile(("塔式", "能力塔", "层层构建", "基座", "塔顶"), min_items=3),
    "iceberg_model": LayoutProfile(("冰山", "显性", "隐性", "表象", "深层", "水面"), min_items=2, max_items=6),
    "funnel": LayoutProfile(("漏斗", "转化", "筛选", "流失", "获客", "成交"), min_items=3),
    "fishbone": LayoutProfile(("鱼骨", "根因", "原因分析", "诱因", "问题原因"), ("medium", "high"), 3),
    "circular_cycle": LayoutProfile(("循环", "周期", "环形", "周而复始", "迭代"), min_items=3, max_items=8),
    "cycle_process": LayoutProfile(("循环流程", "闭环流程", "持续改进", "迭代流程", "反馈循环"), min_items=3),
    "closed_loop_management": LayoutProfile(("闭环管理", "管理闭环", "执行反馈", "监督改进", "pdca"), min_items=3),
    "input_process_output": LayoutProfile(("输入", "过程", "输出", "投入", "产出", "ipo"), min_items=3, max_items=6),
    "swimlane": LayoutProfile(("泳道", "跨部门", "责任人", "职责", "协作流程", "角色分工"), ("medium", "high"), 4),
    "gantt_chart": LayoutProfile(("甘特", "排期", "工期", "进度计划", "开始时间", "完成时间"), ("medium", "high"), 3),
    "road_map": LayoutProfile(("road map", "roadmap", "路线图", "发展路径", "阶段目标", "演进路线"), min_items=3),
    "route_planning": LayoutProfile(("路径规划", "实施路径", "推进路径", "行动路径", "路线规划"), min_items=3),
    "annual_plan": LayoutProfile(("年度规划", "年度计划", "季度", "q1", "q2", "全年"), min_items=4),
    "milestones": LayoutProfile(("里程碑", "关键节点", "重要节点", "阶段成果", "节点目标"), min_items=3),
    "staircase": LayoutProfile(("阶梯", "逐级", "台阶", "拾级", "层层递进"), min_items=3),
    "growth_staircase": LayoutProfile(("成长", "进阶", "成熟度", "升级", "能力提升", "成长阶段"), min_items=3),
    "progressive_relation": LayoutProfile(("递进", "逐步", "由浅入深", "从而", "进一步", "层层深入"), min_items=3),
    "five_step": LayoutProfile(("五步", "五个步骤", "五阶段", "5步", "五步法"), min_items=5, max_items=5),
    "three_part": LayoutProfile(("三段", "三个方面", "三部分", "三步", "三阶段"), min_items=3, max_items=3),
    "goal_strategy_action": LayoutProfile(("目标", "策略", "行动", "举措", "战略落地"), min_items=3, max_items=6),
    "problem_cause_solution": LayoutProfile(("问题", "原因", "方案", "痛点", "根因", "解决"), min_items=3, max_items=8),
    "value_chain": LayoutProfile(("价值链", "价值创造", "业务链", "研发", "生产", "交付"), min_items=3),
    "data_cards": LayoutProfile(("指标", "数据概览", "核心数据", "kpi", "同比", "环比"), ("medium", "high"), 3),
    "big_number": LayoutProfile(("大数字", "关键数字", "核心指标", "总额", "达成率", "增长率"), ("low", "medium"), 1, 4),
    "dashboard": LayoutProfile(("仪表盘", "dashboard", "经营看板", "监控看板", "综合指标"), ("high",), 4),
    "bar_chart": LayoutProfile(("柱状图", "柱形图", "排名", "各项", "分组比较", "数量对比"), min_items=3),
    "line_chart": LayoutProfile(("折线", "趋势", "走势", "连续变化", "增长曲线", "波动"), min_items=3),
    "pie_chart": LayoutProfile(("饼图", "占比", "构成", "份额", "比例", "分布比例"), min_items=2, max_items=8),
    "scatter_plot": LayoutProfile(("散点", "相关性", "分散", "象限分布", "聚类", "离群"), ("medium", "high"), 3),
    "data_table": LayoutProfile(("表格", "明细", "数据表", "台账", "多字段", "详细数据"), ("high",), 4),
    "map_distribution": LayoutProfile(("地图", "区域", "省份", "城市", "地域", "全国分布"), min_items=2),
    "priority_ranking": LayoutProfile(("优先级", "排序", "排名", "重要性", "紧急程度", "优先处理"), min_items=3),
    "floor_plan": LayoutProfile(("户型", "房型", "平面图", "空间布局", "房间", "动线"), min_items=2),
    "people_profile": LayoutProfile(("人物介绍", "个人简介", "创始人", "专家", "团队成员", "履历"), ("low", "medium"), 1, 5),
    "product_showcase": LayoutProfile(("产品展示", "产品介绍", "外观", "产品亮点", "功能卖点", "新品"), ("low", "medium"), 1, 6),
    "case_breakdown": LayoutProfile(("案例", "客户背景", "实施方案", "案例成果", "成功实践"), min_items=3),
    "scenario_showcase": LayoutProfile(("场景", "使用场景", "应用场景", "情境", "体验"), min_items=2),
    "scenario_map": LayoutProfile(("场景地图", "用户旅程", "触点", "场景路径", "全景图"), ("medium", "high"), 3),
    "retrospective": LayoutProfile(("复盘", "总结", "经验", "教训", "改进", "下一步"), min_items=3),
    "achievement_wall": LayoutProfile(("成果", "荣誉", "获奖", "成绩", "案例墙", "成果墙"), min_items=3),
    "magazine_editorial": LayoutProfile(("杂志", "访谈", "故事", "报道", "长文", "观点文章"), ("low", "medium"), 1, 4),
    "full_screen_visual": LayoutProfile(("全屏", "主视觉", "愿景", "口号", "主题发布", "沉浸"), ("low",), 0, 2),
    "hero_with_supporting_cards": LayoutProfile(("核心观点", "核心结论", "主题", "总览", "亮点", "概览"), ("low", "medium"), 1, 4),
    "summary_detail": LayoutProfile(("总分", "概述", "总体", "分别", "展开说明", "一览"), min_items=2),
    "module_combination": LayoutProfile(("模块", "组件", "功能模块", "能力模块", "组合", "解决方案"), ("medium", "high"), 3),
    "grid_n_x_m": LayoutProfile(("并列", "分类", "多个方面", "要点", "维度", "清单"), ("medium", "high"), 3),
    "tag_categories": LayoutProfile(("标签", "分类", "类别", "主题词", "关键词", "分组"), min_items=4),
    "checklist": LayoutProfile(("清单", "检查项", "待办", "注意事项", "要求", "事项"), ("medium", "high"), 4),
    "collage": LayoutProfile(("拼贴", "作品集", "图片集", "照片", "多图", "画廊"), min_items=3),
    "infographic": LayoutProfile(("信息图", "信息图表", "知识图谱", "科普", "数据故事"), min_items=3),
    "visual_metaphor": LayoutProfile(("隐喻", "象征", "比喻", "愿景", "启航", "桥梁", "灯塔"), ("low", "medium"), 1, 4),
    "split_left_right": LayoutProfile(("两部分", "一方面", "另一方面", "图文", "左右"), min_items=2, max_items=5),
    "split_top_bottom": LayoutProfile(("上下", "上层", "下层", "现状与未来", "结论与依据"), min_items=2, max_items=5),
}


def recommend_layout_family(
    title: str,
    summary: str,
    bullets: Sequence[str],
    *,
    page_richness: str = "medium",
    candidate_families: Iterable[str] | None = None,
    previous_family: str = "",
    page_index: int = 0,
    include_cover_page: bool = True,
) -> str:
    candidates = _normalize_candidates(candidate_families)
    text = f"{title} {summary} {' '.join(str(item) for item in bullets)}".lower()
    item_count = len([item for item in bullets if str(item).strip()])
    richness = normalize_page_richness_level(page_richness)
    previous = normalize_layout_family_name(previous_family) if previous_family else ""

    scored = [
        (
            _score_layout(family, text, item_count, richness, page_index, include_cover_page)
            - (5 if family == previous else 0),
            -candidates.index(family),
            family,
        )
        for family in candidates
    ]
    return max(scored)[2] if scored else "grid_n_x_m"


def choose_layout_family(
    suggested_family: str,
    title: str,
    summary: str,
    bullets: Sequence[str],
    **kwargs: object,
) -> str:
    candidates = _normalize_candidates(kwargs.get("candidate_families"))
    recommended = recommend_layout_family(title, summary, bullets, **kwargs)
    suggested = normalize_layout_family_name(suggested_family) if suggested_family else ""
    if not suggested or suggested not in candidates:
        return recommended

    text = f"{title} {summary} {' '.join(str(item) for item in bullets)}".lower()
    item_count = len([item for item in bullets if str(item).strip()])
    richness = normalize_page_richness_level(kwargs.get("page_richness", "medium"))
    page_index = int(kwargs.get("page_index", 0) or 0)
    include_cover_page = bool(kwargs.get("include_cover_page", True))
    suggested_score = _score_layout(suggested, text, item_count, richness, page_index, include_cover_page)
    recommended_score = _score_layout(recommended, text, item_count, richness, page_index, include_cover_page)
    recommended_keyword_score = _keyword_score(recommended, text)
    suggested_keyword_score = _keyword_score(suggested, text)
    should_correct = (
        recommended_keyword_score >= 5
        and recommended_keyword_score > suggested_keyword_score
        and recommended_score >= suggested_score + 6
    )
    return recommended if should_correct else suggested


def _score_layout(family: str, text: str, item_count: int, richness: str, page_index: int, include_cover_page: bool) -> int:
    profile = LAYOUT_PROFILES.get(family, LayoutProfile(()))
    score = _keyword_score(family, text)
    score += 2 if richness in profile.densities else -2
    score += 2 if profile.min_items <= item_count <= profile.max_items else -2
    if page_index == 0 and include_cover_page:
        score += 7 if family in {"hero_with_supporting_cards", "full_screen_visual", "visual_metaphor"} else 0
    if item_count >= 5 and family in {"grid_n_x_m", "module_combination", "data_table", "dashboard", "checklist"}:
        score += 3
    if item_count <= 2 and family in {"full_screen_visual", "big_number", "people_profile", "product_showcase"}:
        score += 3
    return score


def _keyword_score(family: str, text: str) -> int:
    profile = LAYOUT_PROFILES.get(family, LayoutProfile(()))
    return sum(5 for keyword in profile.keywords if keyword.lower() in text)


def _normalize_candidates(values: object) -> list[str]:
    source = values if isinstance(values, (list, tuple, set)) else DEFAULT_LAYOUT_FAMILIES
    result: list[str] = []
    for value in source:
        family = normalize_layout_family_name(str(value))
        if validate_layout_family(family) and family not in result:
            result.append(family)
    return result or list(DEFAULT_LAYOUT_FAMILIES)
