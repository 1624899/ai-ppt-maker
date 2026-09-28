from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from ppt_system.generation.design_grammar import DEFAULT_LAYOUT_FAMILIES, LAYOUT_FAMILY_LABELS


@dataclass(frozen=True)
class LayoutProfile:
    value: str
    label: str
    category: str
    description: str
    suitable_for: tuple[str, ...]
    avoid_for: tuple[str, ...]
    keywords: tuple[str, ...]
    intent_types: tuple[str, ...]
    density_levels: tuple[str, ...]
    min_items: int
    max_items: int
    supports_chart: bool
    supports_image: bool
    supports_text: bool
    visual_strength: str
    semantic_group: str
    visual_axis: str
    related_families: tuple[str, ...]


# 分类用于前端浏览；语义组和视觉方向用于整套编排，三者保持独立。
_GROUPS: dict[str, tuple[str, str, tuple[str, ...], tuple[str, ...], str, str]] = {
    "opening": ("开场与视觉", "以主视觉和简洁信息建立页面主题与情绪。", ("封面", "章节开场", "主题发布"), ("高密度数据", "复杂流程"), "high", "visual"),
    "editorial": ("观点与叙事", "用主张、叙事层级或图文关系突出核心信息。", ("核心观点", "案例叙事", "品牌表达"), ("复杂表格", "多步骤流程"), "high", "visual"),
    "modules": ("并列与模块", "将多个并列要点组织为清晰、均衡的模块。", ("能力介绍", "要点概览", "模块说明"), ("强时序关系", "复杂因果分析"), "medium", "grid"),
    "flow": ("流程与时间", "按步骤、阶段或时间顺序表达推进关系。", ("实施流程", "项目计划", "发展历程"), ("多维数据比较", "无顺序的观点集合"), "medium", "horizontal"),
    "structure": ("关系与结构", "呈现层级、关联、循环或系统性结构。", ("组织架构", "关系网络", "能力体系"), ("简单结论", "高密度表格"), "medium", "radial"),
    "data": ("数据与指标", "用图表、指标或表格传达数据结论。", ("经营指标", "趋势分析", "区域分布"), ("纯叙事内容", "复杂流程"), "medium", "chart"),
    "comparison": ("对比与分析", "突出对象之间的差异、取舍或分析结论。", ("方案比较", "优劣分析", "问题诊断"), ("单一对象介绍", "时间线"), "medium", "split"),
    "showcase": ("产品与场景", "以对象、人物、案例或场景呈现具体价值。", ("产品介绍", "客户案例", "应用场景"), ("高密度指标", "复杂组织关系"), "high", "visual"),
    "management": ("管理与复盘", "用于目标管理、行动安排与结果复盘。", ("年度规划", "优先级", "复盘总结"), ("沉浸式故事", "复杂数据建模"), "medium", "grid"),
}

_FAMILY_GROUPS = {
    "opening": "hero_with_supporting_cards full_screen_visual visual_metaphor",
    "editorial": "magazine_editorial summary_detail split_left_right split_top_bottom infographic",
    "modules": "grid_n_x_m module_combination three_part tag_categories checklist collage",
    "flow": "timeline_horizontal timeline_vertical process_horizontal process_vertical road_map gantt_chart swimlane milestones staircase progressive_relation route_planning five_step annual_plan growth_staircase",
    "structure": "hub_and_spoke circular_cycle cycle_process closed_loop_management org_chart relationship_chain venn_relation layered_structure pyramid_structure tower_structure iceberg_model value_chain ecosystem input_process_output floor_plan",
    "data": "data_cards big_number dashboard bar_chart line_chart pie_chart scatter_plot data_table map_distribution",
    "comparison": "compare_dual_axis comparison_table pros_cons swot fishbone funnel problem_cause_solution goal_strategy_action priority_ranking",
    "showcase": "people_profile product_showcase case_breakdown scenario_showcase scenario_map",
    "management": "retrospective achievement_wall",
}

_KEYWORDS = {
    "timeline": ("时间线", "时间轴", "历程", "阶段", "发展"), "process": ("流程", "步骤", "执行", "环节", "推进"),
    "comparison": ("对比", "比较", "差异", "方案", "优劣"), "data": ("指标", "数据", "同比", "环比", "趋势"),
    "relationship": ("关系", "结构", "体系", "关联", "层级"), "showcase": ("产品", "案例", "场景", "人物", "客户"),
    "management": ("计划", "目标", "复盘", "行动", "成果"), "visual": ("主题", "愿景", "故事", "品牌", "主视觉"),
}

# 不能被分类词替代的专用结构信号，确保特定内容仍优先匹配其专用版式。
_SPECIALIZED_KEYWORDS = {
    "funnel": ("漏斗", "获客", "线索", "成交", "转化", "流失"),
    "gantt_chart": ("甘特", "排期", "工期", "开始时间", "完成时间"),
    "swimlane": ("泳道", "跨部门", "责任人", "角色分工", "审批"),
    "dashboard": ("仪表盘", "经营看板", "综合指标", "dashboard"),
    "line_chart": ("折线", "连续月份", "增长走势", "增长曲线", "波动"),
    "bar_chart": ("柱状图", "排名", "分类数值", "分组比较"),
    "compare_dual_axis": ("两个方案", "两组方案", "双轴", "优劣", "差异"),
    "comparison_table": ("对照表", "多维对比", "参数对比"),
    "org_chart": ("组织架构", "汇报关系", "部门", "岗位"),
    "map_distribution": ("地图", "省份", "城市", "区域分布"),
}

_SIGNALS = {
    "timeline": ("timeline", "low", "medium", 2, 6), "process": ("process", "medium", "high", 2, 6),
    "comparison": ("comparison", "medium", "high", 2, 8), "data": ("data_analysis", "medium", "high", 2, 12),
    "relationship": ("relationship", "medium", "high", 2, 8), "showcase": ("product_showcase", "low", "medium", 1, 6),
    "management": ("action_plan", "medium", "high", 3, 10), "visual": ("key_message", "low", "medium", 1, 4),
}


def _family_group(value: str) -> str:
    return next((group for group, families in _FAMILY_GROUPS.items() if value in families.split()), "modules")


def _signal_key(value: str, group: str) -> str:
    if any(token in value for token in ("timeline", "gantt", "road", "milestone", "annual", "route")):
        return "timeline"
    if any(token in value for token in ("process", "swimlane", "five_step", "input_", "staircase", "progressive")):
        return "process"
    if group == "comparison": return "comparison"
    if group == "data": return "data"
    if group == "structure": return "relationship"
    if group == "showcase": return "showcase"
    if group == "management": return "management"
    return "visual" if group in {"opening", "editorial"} else "management"


def _build_profile(value: str) -> LayoutProfile:
    group = _family_group(value)
    category, base_description, suitable, avoid, strength, axis = _GROUPS[group]
    signal = _signal_key(value, group)
    intent, low_density, high_density, min_items, max_items = _SIGNALS[signal]
    if value in {"dashboard", "data_table", "comparison_table"}: low_density, high_density = "high", "high"
    if value in {"full_screen_visual", "visual_metaphor", "big_number"}: low_density, high_density, max_items = "low", "low", 2
    chart = group == "data" or value in {"funnel", "gantt_chart", "comparison_table"}
    image = group in {"opening", "editorial", "showcase"} or value in {"collage", "map_distribution", "floor_plan"}
    return LayoutProfile(value, LAYOUT_FAMILY_LABELS[value], category, base_description, suitable, avoid,
        _SPECIALIZED_KEYWORDS.get(value, _KEYWORDS[signal]), (intent,), (low_density,) if low_density == high_density else (low_density, high_density),
        min_items, max_items, chart, image, not image or group != "opening", strength, group if value not in {"circular_cycle", "cycle_process", "closed_loop_management"} else "cycle", axis,
        tuple(item for item in DEFAULT_LAYOUT_FAMILIES if item != value and _family_group(item) == group)[:3])


LAYOUT_PROFILES: dict[str, LayoutProfile] = {value: _build_profile(value) for value in DEFAULT_LAYOUT_FAMILIES}


def export_layout_profiles(path: str | Path) -> None:
    """将当前注册表导出为 UTF-8 JSON，供设计侧在外部文件中维护。"""
    target = Path(path)
    target.write_text(json.dumps(build_layout_profile_options(), ensure_ascii=False, indent=2), encoding="utf-8")


def load_layout_profiles(path: str | Path) -> dict[str, LayoutProfile]:
    """校验并加载外部画像，机器值必须与已注册的 68 个版式完全一致。"""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    items = raw.get("items", raw) if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise ValueError("版式画像文件必须是数组或包含 items 数组")
    required = set(LayoutProfile.__dataclass_fields__)
    values = {str(item.get("value")) for item in items if isinstance(item, dict)}
    if values != set(DEFAULT_LAYOUT_FAMILIES):
        raise ValueError("外部版式画像必须完整覆盖已注册的 68 个版式")
    if any(not required.issubset(item) for item in items if isinstance(item, dict)):
        raise ValueError("外部版式画像缺少必填字段")
    return {str(item["value"]): LayoutProfile(**{key: tuple(value) if isinstance(value, list) else value for key, value in item.items() if key in required}) for item in items}

# 房型图的核心是平面分区与动线，不应使用通用结构关系的说明。
LAYOUT_PROFILES["floor_plan"] = LayoutProfile(
    value="floor_plan",
    label="房型图",
    category="产品与场景",
    description="用平面分区和空间动线展示区域布局、功能分配或服务触点关系。",
    suitable_for=("空间布局", "园区导览", "门店分区", "用户旅程触点", "服务流程地图"),
    avoid_for=("组织架构", "高密度数据分析", "多维方案对比"),
    keywords=("户型", "房型", "平面图", "空间布局", "区域", "动线", "分区"),
    intent_types=("relationship", "scenario"),
    density_levels=("medium", "high"),
    min_items=2,
    max_items=8,
    supports_chart=False,
    supports_image=True,
    supports_text=True,
    visual_strength="medium",
    semantic_group="spatial_map",
    visual_axis="spatial",
    related_families=("scenario_map", "map_distribution", "scenario_showcase"),
)

# 逐版式说明覆盖分类级默认文案，避免用户看到与实际构图无关的泛化描述。
_PROFILE_DETAILS: dict[str, tuple[str, tuple[str, ...]]] = {
    "compare_dual_axis": ("将两组对象左右并列，并按相同维度对照差异，突出结论和取舍。", ("方案对比", "竞品分析", "前后变化")),
    "grid_n_x_m": ("以规则网格并列多个信息单元，便于快速扫描同层级要点。", ("能力清单", "功能模块", "多维要点")),
    "timeline_horizontal": ("沿横向时间轴展示少量关键节点，突出阶段推进与先后关系。", ("发展历程", "产品演进", "项目节点")),
    "timeline_vertical": ("沿纵向时间轴承载较多事件和补充说明，适合连续叙事。", ("大事记", "历史沿革", "阶段记录")),
    "split_left_right": ("将两类内容左右分置，适合图文配合或两个角度的并列阐述。", ("图文说明", "现状与目标", "双主题表达")),
    "split_top_bottom": ("将结论与依据上下分层，形成由概览到说明的阅读顺序。", ("结论与依据", "现状与未来", "上下层信息")),
    "process_horizontal": ("以从左到右的步骤串联展示短流程，强调执行顺序和完成路径。", ("业务流程", "实施步骤", "交付路径")),
    "process_vertical": ("以纵向步骤承载较长说明，适合分阶段执行与审批流程。", ("审批流程", "分阶段实施", "操作说明")),
    "hero_with_supporting_cards": ("用一个核心主张配合辅助信息卡，突出主题并补充关键亮点。", ("封面", "核心结论", "主题概览")),
    "magazine_editorial": ("以主视觉、窄栏文字和重点引文组织内容，形成报道或编辑专题感。", ("人物故事", "案例报道", "品牌叙事")),
    "full_screen_visual": ("以单一强主视觉和极少文字建立沉浸感与情绪张力。", ("封面", "章节页", "品牌宣言")),
    "funnel": ("用由宽到窄的层级展示筛选、转化或流失过程，并突出各阶段规模。", ("销售转化", "用户漏斗", "渠道筛选")),
    "staircase": ("以阶梯形态表现逐级提升、阶段门槛或能力成长。", ("能力升级", "阶段目标", "成熟度演进")),
    "progressive_relation": ("用连续递进的模块说明从前提到结果的层层推进关系。", ("逻辑推演", "能力递进", "策略展开")),
    "road_map": ("将阶段目标、重点动作和关键产出排布在路线图上，展示长期推进方向。", ("战略路线图", "产品规划", "转型路径")),
    "gantt_chart": ("以时间条展示任务起止、并行关系和项目排期。", ("项目排期", "研发计划", "交付进度")),
    "swimlane": ("按角色或部门划分泳道，清楚呈现跨团队责任和交接流程。", ("跨部门协作", "审批流程", "服务交付")),
    "data_cards": ("以多个指标卡并列呈现核心数值、同比环比和简短结论。", ("经营概览", "核心 KPI", "数据快报")),
    "big_number": ("用放大的关键数字作为视觉中心，强化单项成果或核心结论。", ("业绩亮点", "关键成果", "核心指标")),
    "dashboard": ("组合多个指标、图表和状态组件，形成高密度的数据总览看板。", ("经营看板", "运营监控", "综合指标")),
    "bar_chart": ("用柱形高度比较不同分类或对象的数值差异与排名。", ("分类比较", "排名分析", "销量对比")),
    "line_chart": ("用连续折线展示时间序列的变化趋势、拐点和波动。", ("趋势分析", "月度变化", "增长走势")),
    "pie_chart": ("用扇形占比呈现整体构成，突出各部分所占份额。", ("占比分析", "结构构成", "市场份额")),
    "scatter_plot": ("以散点位置揭示两个指标的相关性、聚类和异常点。", ("相关性分析", "象限分析", "客群分布")),
    "data_table": ("用行列对齐展示多字段明细，便于精确查阅和横向核对。", ("数据明细", "参数清单", "经营台账")),
    "map_distribution": ("将数值或对象标注在地图区域上，展示地域覆盖和分布差异。", ("区域分布", "市场覆盖", "门店布局")),
    "people_profile": ("以人物照片、身份标签和经历要点快速建立人物认知。", ("团队介绍", "专家简介", "创始人故事")),
    "product_showcase": ("以产品主图搭配卖点标注，突出外观、功能与价值。", ("产品发布", "功能亮点", "新品介绍")),
    "case_breakdown": ("按背景、行动和成果拆解案例，说明可复制的方法与价值。", ("客户案例", "成功实践", "项目复盘")),
    "problem_cause_solution": ("将问题、根因与解决方案串联，形成从诊断到行动的闭环。", ("问题诊断", "改进方案", "痛点分析")),
    "goal_strategy_action": ("按目标、策略和行动拆分规划，明确从方向到落地的对应关系。", ("战略落地", "行动计划", "经营规划")),
    "summary_detail": ("先给出总体结论，再展开关键细节，适合总分式信息表达。", ("执行摘要", "方案概述", "结论展开")),
    "module_combination": ("以大小不同的模块组合表现能力构成和模块之间的协同。", ("解决方案", "能力体系", "产品模块")),
    "collage": ("将多张图片或内容碎片拼贴成视觉集合，强调丰富性和氛围。", ("作品集", "活动回顾", "多图展示")),
    "tag_categories": ("用标签分组归纳关键词、主题或对象类别，适合轻量分类。", ("关键词云", "主题分类", "用户标签")),
    "checklist": ("按清单逐项展示待办、要求或检查标准，强调执行完整性。", ("行动清单", "检查事项", "交付要求")),
    "milestones": ("突出少数关键里程碑及其成果，适合阶段性汇报。", ("项目节点", "阶段成果", "关键事件")),
    "priority_ranking": ("根据重要性、紧急度或价值对事项排序，辅助决策取舍。", ("优先级管理", "事项排序", "资源投入")),
    "three_part": ("以等宽三段展示固定的三类内容或三个阶段。", ("三项原则", "三大能力", "三阶段规划")),
    "five_step": ("以固定五步结构拆解方法论或标准执行流程。", ("五步法", "实施方法", "标准流程")),
    "comparison_table": ("用行列对照多个对象与比较维度，适合参数较多的横向比较。", ("功能对比", "方案选型", "参数比较")),
    "pros_cons": ("将正反两面并置，直观呈现方案的优点、缺点和取舍。", ("利弊分析", "方案评估", "决策讨论")),
    "swot": ("以四象限整理优势、劣势、机会和威胁，形成战略分析全景。", ("SWOT 分析", "战略诊断", "竞争分析")),
    "fishbone": ("以鱼骨分支追溯问题的多类根因，适合系统性诊断。", ("根因分析", "质量改进", "问题排查")),
    "growth_staircase": ("用上升阶梯表达个人、产品或组织从当前状态到目标状态的成长路径。", ("成长路径", "能力进阶", "成熟度模型")),
    "route_planning": ("用路径节点串联实施路线，突出关键动作、选择点和到达目标。", ("实施路径", "用户路径", "推进路线")),
    "annual_plan": ("按年度或季度排布目标、重点工作和交付成果，支持节奏化管理。", ("年度规划", "季度计划", "经营安排")),
    "retrospective": ("回顾目标、结果、经验和改进项，形成可执行的复盘结论。", ("项目复盘", "经营总结", "经验沉淀")),
    "achievement_wall": ("以奖项、数据和成果卡片集中陈列阶段性成绩与背书。", ("成果展示", "荣誉展示", "年度回顾")),
    "scenario_showcase": ("通过具体使用场景呈现对象如何解决问题和创造价值。", ("应用场景", "客户体验", "服务示例")),
    "scenario_map": ("按场景、角色和触点绘制全景地图，呈现体验流程和机会点。", ("用户旅程", "服务蓝图", "场景全景")),
    "infographic": ("将文字、图标和数字融合为一张信息图，快速讲清复杂知识。", ("知识科普", "数据故事", "概念说明")),
    "visual_metaphor": ("借助具象隐喻画面表达抽象主题，增强记忆点和情绪感染力。", ("愿景表达", "品牌主题", "章节开场")),
}

for _value, (_description, _suitable_for) in _PROFILE_DETAILS.items():
    _profile = LAYOUT_PROFILES[_value]
    LAYOUT_PROFILES[_value] = replace(_profile, description=_description, suitable_for=_suitable_for)

_PROFILE_KEYWORD_OVERRIDES = {
    "grid_n_x_m": ("并列", "网格", "模块", "要点", "多维", "清单"),
    "split_left_right": ("左右", "图文", "两部分", "现状", "目标"),
    "split_top_bottom": ("上下", "结论", "依据", "现状", "未来"),
    "magazine_editorial": ("杂志", "访谈", "故事", "报道", "长文", "引文"),
    "pie_chart": ("饼图", "占比", "构成", "份额", "比例"),
    "scatter_plot": ("散点", "相关性", "聚类", "象限", "离群"),
    "data_table": ("表格", "明细", "台账", "字段", "参数"),
    "module_combination": ("模块", "组件", "能力模块", "组合", "协同"),
    "collage": ("拼贴", "作品集", "图片集", "照片", "画廊"),
    "tag_categories": ("标签", "分类", "类别", "关键词", "分组"),
    "checklist": ("清单", "检查项", "待办", "要求", "事项"),
    "three_part": ("三段", "三个方面", "三部分", "三阶段"),
    "retrospective": ("复盘", "总结", "经验", "教训", "改进", "下一步"),
    "achievement_wall": ("成果", "荣誉", "获奖", "成绩", "案例墙"),
}
for _value, _keywords in _PROFILE_KEYWORD_OVERRIDES.items():
    LAYOUT_PROFILES[_value] = replace(LAYOUT_PROFILES[_value], keywords=_keywords)


# 关系与循环版式的图形语义差异显著，必须使用专属说明，不能复用通用结构描述。
_STRUCTURE_PROFILE_OVERRIDES: dict[str, dict[str, object]] = {
    "hub_and_spoke": {"description": "以中心主题向外连接多个分支，突出核心与辐射范围。", "suitable_for": ("核心能力", "业务全景", "中心议题与分支"), "avoid_for": ("严格时间顺序", "多层级汇报关系"), "semantic_group": "hub"},
    "pyramid_structure": {"description": "用由底至顶的层级表达支撑关系、优先级或能力递进。", "suitable_for": ("战略分层", "能力体系", "价值优先级"), "avoid_for": ("平级模块", "循环关系"), "semantic_group": "pyramid", "visual_axis": "vertical"},
    "org_chart": {"description": "用上下级节点和连接关系展示组织层级、部门归属与汇报路径。", "suitable_for": ("组织架构", "团队分工", "汇报关系"), "avoid_for": ("跨组织协同网络", "时间计划"), "semantic_group": "organization", "visual_axis": "vertical"},
    "relationship_chain": {"description": "按链路串联主体或环节，说明上下游依赖、传导路径和影响关系。", "suitable_for": ("业务链路", "上下游关系", "影响传导"), "avoid_for": ("中心辐射结构", "无顺序的模块列表"), "semantic_group": "chain", "visual_axis": "horizontal"},
    "venn_relation": {"description": "通过相交区域突出多个对象之间的共性、边界与重叠价值。", "suitable_for": ("共同能力", "用户交集", "范围重叠"), "avoid_for": ("三层以上层级", "时间推进"), "semantic_group": "overlap"},
    "layered_structure": {"description": "用分层版面说明系统组成、架构边界和各层职责。", "suitable_for": ("技术架构", "能力分层", "平台分层"), "avoid_for": ("组织汇报关系", "闭环流程"), "semantic_group": "layers", "visual_axis": "vertical"},
    "value_chain": {"description": "连接价值创造的前后环节，突出从投入到交付的业务协同。", "suitable_for": ("业务价值链", "产业链", "端到端交付"), "avoid_for": ("部门层级", "简单观点总结"), "semantic_group": "value_chain", "visual_axis": "horizontal"},
    "ecosystem": {"description": "围绕核心主体展示多方参与者、资源连接和协同生态。", "suitable_for": ("合作生态", "利益相关方", "平台网络"), "avoid_for": ("线性执行流程", "单一组织架构"), "semantic_group": "ecosystem"},
    "input_process_output": {"description": "用输入、处理和输出三个阶段说明系统或业务的转化逻辑。", "suitable_for": ("业务机制", "服务交付", "系统运行逻辑"), "avoid_for": ("多轮循环", "复杂时间排期"), "semantic_group": "ipo", "visual_axis": "horizontal"},
    "iceberg_model": {"description": "用水面上下的分层区分可见现象与深层原因、能力或风险。", "suitable_for": ("根因分析", "隐性能力", "风险诊断"), "avoid_for": ("并列要点", "项目时间线"), "semantic_group": "iceberg", "visual_axis": "vertical"},
    "tower_structure": {"description": "以塔基到塔尖的堆叠结构表达能力建设、支撑关系和目标高度。", "suitable_for": ("能力建设", "战略支撑", "成熟度模型"), "avoid_for": ("平行模块", "网络关系"), "semantic_group": "tower", "visual_axis": "vertical"},
    "circular_cycle": {"description": "用环形节点展示持续循环、周期迭代或多阶段往复关系。", "suitable_for": ("迭代周期", "生命周期", "持续改善"), "avoid_for": ("一次性线性流程", "层级结构"), "semantic_group": "cycle"},
    "cycle_process": {"description": "将执行步骤首尾闭合，强调流程完成后的反馈与再次启动。", "suitable_for": ("业务闭环", "持续运营", "迭代流程"), "avoid_for": ("无反馈的标准流程", "项目排期"), "semantic_group": "cycle_process"},
    "closed_loop_management": {"description": "围绕目标、执行、检查和改进构建管理闭环，突出责任与反馈机制。", "suitable_for": ("管理机制", "PDCA", "运营复盘"), "avoid_for": ("简单循环展示", "产品功能介绍"), "semantic_group": "management_cycle"},
}

for _value, _override in _STRUCTURE_PROFILE_OVERRIDES.items():
    _profile = LAYOUT_PROFILES[_value]
    LAYOUT_PROFILES[_value] = LayoutProfile(
        value=_profile.value,
        label=_profile.label,
        category=_profile.category,
        description=str(_override["description"]),
        suitable_for=tuple(_override["suitable_for"]),
        avoid_for=tuple(_override["avoid_for"]),
        keywords=_profile.keywords,
        intent_types=_profile.intent_types,
        density_levels=_profile.density_levels,
        min_items=_profile.min_items,
        max_items=_profile.max_items,
        supports_chart=_profile.supports_chart,
        supports_image=_profile.supports_image,
        supports_text=_profile.supports_text,
        visual_strength=_profile.visual_strength,
        semantic_group=str(_override["semantic_group"]),
        visual_axis=str(_override.get("visual_axis", _profile.visual_axis)),
        related_families=_profile.related_families,
    )

# 补齐流程类版式的实际构图方向与限制，避免整套编排把纵向结构误判为横向结构。
_FLOW_PROFILE_OVERRIDES = {
    "timeline_vertical": {"visual_axis": "vertical", "avoid_for": ("少量关键节点", "无时间顺序的模块列表")},
    "process_vertical": {"visual_axis": "vertical", "avoid_for": ("短步骤横向流程", "无先后关系的并列观点")},
    "swimlane": {"visual_axis": "lane", "avoid_for": ("单角色短流程", "无责任归属的概念说明")},
    "gantt_chart": {"visual_axis": "schedule", "avoid_for": ("没有起止时间的事项列表", "即时性短流程")},
    "road_map": {"visual_axis": "path", "avoid_for": ("详细任务排期", "无阶段目标的观点集合")},
    "route_planning": {"visual_axis": "path", "avoid_for": ("精确工期管理", "无路径关系的并列清单")},
    "annual_plan": {"visual_axis": "schedule", "avoid_for": ("单次活动流程", "没有时间周期的策略说明")},
    "dashboard": {"avoid_for": ("单一指标结论", "纯叙事内容")},
    "big_number": {"avoid_for": ("需要解释多个维度的复杂数据", "长段落说明")},
    "pie_chart": {"avoid_for": ("时间趋势", "类别超过八组的复杂构成")},
    "data_table": {"avoid_for": ("需要突出单一结论", "低信息量的概览页")},
    "collage": {"avoid_for": ("需要精确比较的数值", "严格步骤关系")},
    "tag_categories": {"avoid_for": ("需要表达先后顺序", "需要展示数值差异")},
    "checklist": {"avoid_for": ("需要表达复杂依赖关系", "强调视觉叙事的封面")},
}

for _value, _override in _FLOW_PROFILE_OVERRIDES.items():
    _profile = LAYOUT_PROFILES[_value]
    LAYOUT_PROFILES[_value] = replace(
        _profile,
        visual_axis=str(_override.get("visual_axis", _profile.visual_axis)),
        avoid_for=tuple(_override.get("avoid_for", _profile.avoid_for)),
    )


def get_layout_profile(value: str) -> LayoutProfile:
    return LAYOUT_PROFILES[value]


def build_layout_profile_options(families: list[str] | None = None) -> list[dict]:
    source = families if families is not None else DEFAULT_LAYOUT_FAMILIES
    return [{"value": p.value, "label": p.label, "category": p.category, "description": p.description,
             "suitable_for": list(p.suitable_for), "avoid_for": list(p.avoid_for), "density_levels": list(p.density_levels),
             "intent_types": list(p.intent_types), "min_items": p.min_items, "max_items": p.max_items,
             "keywords": list(p.keywords), "related_families": list(p.related_families),
             "supports_chart": p.supports_chart, "supports_image": p.supports_image, "supports_text": p.supports_text,
             "visual_strength": p.visual_strength, "semantic_group": p.semantic_group, "visual_axis": p.visual_axis}
            for value in source if value in LAYOUT_PROFILES for p in [LAYOUT_PROFILES[value]]]


# 生产环境优先读取可审阅的 JSON 画像；文件缺失或校验失败时保留代码注册表，保证历史任务可用。
_EXTERNAL_PROFILE_PATH = Path(__file__).with_name("layout_profiles.json")
if _EXTERNAL_PROFILE_PATH.exists():
    try:
        LAYOUT_PROFILES = load_layout_profiles(_EXTERNAL_PROFILE_PATH)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
