"""68 种版式的本地确定性蓝图目录。"""
from __future__ import annotations

from typing import Callable


Shape = dict[str, object]


def _s(kind, label, x, y, w, h, decorative=False):
    return {"kind": kind, "label": label, "left": x, "top": y, "width": w, "height": h, "decorative": decorative}


def _title(): return [_s("title", "标题", 55, 28, 500, 46)]
def _grid(labels, cols=2):
    rows = (len(labels) + cols - 1) // cols; gap = 24; w = (880 - gap * (cols - 1)) / cols; h = (390 - gap * (rows - 1)) / rows
    return _title() + [_s("rect", label, 60 + (i % cols) * (w + gap), 125 + (i // cols) * (h + gap), w, h) for i, label in enumerate(labels)]
def _horizontal(labels, kind="rect"):
    gap=24; w=(860-gap*(len(labels)-1))/len(labels)
    return _title()+[_s("line-h","",90,300,820,7,True)]+[_s(kind,label,70+i*(w+gap),230,w,145) for i,label in enumerate(labels)]
def _vertical(labels, stagger=0):
    h=310/len(labels)
    return _title()+[_s("line-v","",145,140,7,340,True)]+[_s("rect",label,190+i*stagger,125+i*(h+12),700-i*stagger,h) for i,label in enumerate(labels)]
def _split(left="正文", right="主视觉"):
    return _title()+[_s("rect",left,60,115,405,390),_s("visual",right,515,95,425,410)]
def _radial(labels, center="中心"):
    pos=[(410,105),(700,225),(580,415),(180,415),(70,225)]; nodes=[_s("circle",label,*pos[i],120,78) for i,label in enumerate(labels[:5])]
    return _title()+nodes+[_s("circle-center",center,405,250,190,118)]
def _bands(labels, kind="rect"):
    h=320/len(labels)
    return _title()+[_s(kind,label,110+i*25,130+i*(h+10),780-i*50,h) for i,label in enumerate(labels)]
def _chart(kind):
    base=_title()+[_s("axis-x","",120,475,760,5,True),_s("axis-y","",120,130,5,350,True)]
    if kind=="bar": return base+[_s("bar",f"数据{i+1}",180+i*135,410-i*55,75,65+i*55) for i in range(5)]
    if kind=="line": return base+[_s("line-node",f"节点{i+1}",170+i*150,390-(i%3)*85,34,34) for i in range(5)]+[_s("trend-line","",180,205,650,210,True)]
    if kind=="pie": return _title()+[_s("pie", "占比",270,135,430,350),_s("legend","图例",735,165,180,260)]
    if kind=="scatter": return base+[_s("dot",f"点{i+1}",180+(i*113)%620,180+(i*71)%240,28,28) for i in range(8)]
    return base


def _floor_plan():
    return [
        _s("roof", "", 35, 55, 930, 95, True),
        _s("title", "总主题", 290, 82, 420, 48),
        _s("room-header", "用户现状", 45, 158, 180, 38, True),
        _s("room-header", "核心方案", 245, 158, 510, 38, True),
        _s("room-header", "服务价值", 775, 158, 180, 38, True),
        _s("side-room", "现状与需求", 45, 205, 180, 300),
        _s("main-room", "", 245, 205, 510, 300, True),
        _s("arrow-left", "输入1", 270, 285, 115, 48),
        _s("arrow-left", "输入2", 270, 365, 115, 48),
        _s("hub", "核心能力", 455, 320, 95, 95),
        _s("hub-node", "能力1", 455, 235, 95, 58),
        _s("hub-node", "能力2", 565, 300, 95, 58),
        _s("hub-node", "能力3", 500, 425, 95, 58),
        _s("hub-node", "能力4", 390, 400, 95, 58),
        _s("arrow-right", "输出1", 620, 285, 110, 48),
        _s("arrow-right", "输出2", 620, 365, 110, 48),
        _s("side-room", "成果与说明", 775, 205, 180, 300),
        _s("foundation", "统一支撑能力", 45, 515, 910, 25, True),
    ]
def _magazine(): return _title()+[_s("visual","主图",55,105,540,285),_s("text-column","正文栏",625,105,145,400),_s("text-column","正文栏",790,105,145,400),_s("caption","引文",55,415,540,90)]
def _full_visual(): return [_s("visual","全屏视觉",20,20,960,522),_s("hero-title","标题",80,365,650,105)]
def _cycle(labels): return _title()+_radial(labels,"循环")[1:-1]+[_s("ring","循环路径",245,130,510,350,True)]
def _pyramid(labels): return _title()+[_s("pyramid",label,360-i*65,135+i*82,280+i*130,58) for i,label in enumerate(labels)]
def _funnel(labels): return _title()+[_s("funnel",label,190+i*70,125+i*85,620-i*140,62) for i,label in enumerate(labels)]
def _stairs(labels): return _title()+[_s("stair",label,100+i*175,400-i*80,170,105+i*20) for i,label in enumerate(labels)]
def _gantt(): return _title()+[_s("gantt-row",f"任务{i+1}",80,135+i*75,820,55) for i in range(5)]+[_s("gantt-bar","周期",260+i*90,150+i*75,220+(i%2)*110,24) for i in range(5)]
def _swimlane(): return _title()+[_s("lane",f"角色{i+1}",70,120+i*110,860,92) for i in range(3)]+[_s("process-node",f"节点{i+1}",220+i*180,145+(i%3)*110,125,45) for i in range(4)]
def _org(): return _title()+[_s("org-root","负责人",400,110,200,70),_s("org-node","部门1",120,265,190,75),_s("org-node","部门2",405,265,190,75),_s("org-node","部门3",690,265,190,75),_s("org-leaf","岗位",170,410,130,60),_s("org-leaf","岗位",435,410,130,60),_s("org-leaf","岗位",700,410,130,60)]
def _venn(): return _title()+[_s("venn","集合A",190,145,390,310),_s("venn","集合B",420,145,390,310),_s("intersection","交集",425,230,150,130)]
def _big_number(): return _title()+[_s("big-number","核心指标",90,125,520,270),_s("metric","指标1",650,125,280,105),_s("metric","指标2",650,250,280,105),_s("metric","指标3",650,375,280,105)]
def _dashboard(): return _title()+[_s("metric","指标1",60,110,205,105),_s("metric","指标2",285,110,205,105),_s("metric","指标3",510,110,205,105),_s("metric","指标4",735,110,205,105),_s("chart-panel","趋势",60,240,560,265),_s("chart-panel","构成",645,240,295,265)]
def _table(): return _title()+[_s("table-head","表头",65,120,870,65)]+[_s("table-row",f"数据行{i+1}",65,195+i*70,870,58) for i in range(4)]
def _map(): return _title()+[_s("map","地图",55,100,700,420),_s("map-pin","区域1",200,210,55,55),_s("map-pin","区域2",440,150,55,55),_s("map-pin","区域3",560,340,55,55),_s("legend","图例",785,135,150,320)]
def _profile(): return _title()+[_s("portrait","人物",70,115,320,390),_s("profile","基本信息",430,115,500,120),_s("profile","经历",430,255,500,110),_s("profile","成果",430,385,500,120)]
def _product(): return _title()+[_s("product","产品",330,120,340,300)]+[_s("feature",f"卖点{i+1}",50+(i%2)*720,145+(i//2)*175,220,110) for i in range(4)]
def _summary_detail(): return _title()+[_s("summary","总论",335,125,330,120)]+[_s("detail",f"分论{i+1}",75+i*225,330,190,145) for i in range(4)]
def _collage(): return _title()+[_s("visual","主图",55,105,500,260),_s("visual","图2",580,105,355,155),_s("visual","图3",580,285,355,220),_s("visual","图4",55,390,240,115),_s("caption","说明",315,390,240,115)]
def _tags(): return _title()+[_s("tag",label,80+(i%3)*295,130+(i//3)*115,245,70) for i,label in enumerate(["分类A","分类B","分类C","标签1","标签2","标签3","标签4","标签5","标签6"])]
def _checklist(): return _title()+[_s("check","✓",80,130+i*78,58,58,True) for i in range(5)]+[_s("list-row",f"事项{i+1}",155,130+i*78,760,58) for i in range(5)]
def _priority(): return _title()+[_s("rank",str(i+1),80,125+i*85,70,65) for i in range(4)]+[_s("priority",f"优先事项{i+1}",175,125+i*85,700-i*75,65) for i in range(4)]
def _fishbone(): return _title()+[_s("bone-main","主骨",120,295,700,8,True),_s("effect","结果",825,245,130,105)]+[_s("bone","原因",180+i*145,150+(i%2)*205,125,82) for i in range(4)]
def _iceberg(): return _title()+[_s("water","水面",60,275,880,8,True),_s("ice-visible","显性",320,125,360,125),_s("ice-hidden","隐性",185,305,630,200)]
def _scenario_map(): return _title()+[_s("map","场景地图",55,105,890,400)]+[_s("map-pin",f"场景{i+1}",160+i*210,180+(i%2)*160,70,70) for i in range(4)]
def _infographic(): return _title()+[_s("big-number","核心数据",60,120,300,175),_s("pie","占比",390,120,250,210),_s("bar","趋势",690,120,250,210),_s("fact","事实1",60,360,275,125),_s("fact","事实2",365,360,275,125),_s("fact","事实3",670,360,275,125)]


FACTORIES: dict[str, Callable[[], list[Shape]]] = {
    "grid_n_x_m": lambda:_grid(["模块1","模块2","模块3","模块4"]), "timeline_horizontal":lambda:_horizontal(["时间1","时间2","时间3","时间4"],"circle"), "timeline_vertical":lambda:_vertical(["时间1","时间2","时间3","时间4"]), "hub_and_spoke":lambda:_radial(["分支1","分支2","分支3","分支4"],"主题"),
    "split_left_right":lambda:_split(), "split_top_bottom":lambda:_title()+[_s("visual","上部视觉",60,105,880,230),_s("rect","下部正文",60,365,880,140)], "compare_dual_axis":lambda:_title()+[_s("compare","方案A",60,125,390,350),_s("axis","比较维度",455,180,90,245),_s("compare","方案B",550,125,390,350)],
    "process_horizontal":lambda:_horizontal(["步骤1","步骤2","步骤3"],"process-node"), "process_vertical":lambda:_vertical(["步骤1","步骤2","步骤3"]), "hero_with_supporting_cards":lambda:_title()+[_s("visual","主视觉",150,100,700,220)]+[_s("rect",f"卡片{i+1}",65+i*310,365,250,135) for i in range(3)],
    "floor_plan":_floor_plan, "magazine_editorial":_magazine, "full_screen_visual":_full_visual, "circular_cycle":lambda:_cycle(["阶段1","阶段2","阶段3","阶段4"]), "pyramid_structure":lambda:_pyramid(["顶层","中层1","中层2","基础层"]), "funnel":lambda:_funnel(["流量","筛选","转化","结果"]), "staircase":lambda:_stairs(["阶段1","阶段2","阶段3","阶段4"]),
    "progressive_relation":lambda:_horizontal(["起点","发展","深化","结果"],"arrow-node"), "road_map":lambda:_horizontal(["现在","近期","中期","远期"],"road-node"), "gantt_chart":_gantt, "cycle_process":lambda:_cycle(["输入","处理","检查","改进"]), "swimlane":_swimlane, "org_chart":_org, "relationship_chain":lambda:_horizontal(["主体A","关系1","主体B","结果"],"chain-node"), "venn_relation":_venn,
    "data_cards":lambda:_grid(["指标1","指标2","指标3","指标4"],4), "big_number":_big_number, "dashboard":_dashboard, "bar_chart":lambda:_chart("bar"), "line_chart":lambda:_chart("line"), "pie_chart":lambda:_chart("pie"), "scatter_plot":lambda:_chart("scatter"), "data_table":_table, "map_distribution":_map,
    "people_profile":_profile, "product_showcase":_product, "case_breakdown":lambda:_horizontal(["背景","做法","成果"],"case"), "problem_cause_solution":lambda:_horizontal(["问题","原因","方案"],"arrow-node"), "goal_strategy_action":lambda:_vertical(["目标","策略","行动"]), "summary_detail":_summary_detail, "layered_structure":lambda:_bands(["战略层","管理层","执行层"]), "module_combination":lambda:_grid(["主模块","模块2","模块3","模块4","模块5"],3), "collage":_collage, "tag_categories":_tags, "checklist":_checklist,
    "milestones":lambda:_horizontal(["里程碑1","里程碑2","里程碑3","里程碑4"],"flag"), "priority_ranking":_priority, "value_chain":lambda:_horizontal(["研发","生产","营销","服务"],"chevron"), "ecosystem":lambda:_radial(["伙伴","客户","平台","服务","资源"],"生态核心"), "closed_loop_management":lambda:_cycle(["计划","执行","检查","改进"]), "input_process_output":lambda:_horizontal(["输入","过程","输出"],"arrow-node"), "three_part":lambda:_grid(["第一部分","第二部分","第三部分"],3), "five_step":lambda:_horizontal(["步骤1","步骤2","步骤3","步骤4","步骤5"],"process-node"),
    "comparison_table":lambda:_title()+[_s("table-head","对比维度",60,120,880,60)]+[_s("table-row",f"对比项{i+1}",60,195+i*72,880,60) for i in range(4)], "pros_cons":lambda:_title()+[_s("pros","优势",60,125,420,350),_s("cons","劣势",520,125,420,350)], "swot":lambda:_grid(["优势 S","劣势 W","机会 O","威胁 T"]), "fishbone":_fishbone, "iceberg_model":_iceberg, "tower_structure":lambda:_bands(["顶层","中层","基层"],"tower"), "growth_staircase":lambda:_stairs(["起步","成长","成熟","领先"]), "route_planning":lambda:_horizontal(["起点","节点1","节点2","终点"],"route-node"), "annual_plan":lambda:_grid(["Q1","Q2","Q3","Q4"],4),
    "retrospective":lambda:_grid(["目标","成果","问题","改进"]), "achievement_wall":lambda:_grid(["成果1","成果2","成果3","成果4","成果5","成果6"],3), "scenario_showcase":lambda:_grid(["场景1","场景2","场景3"],3), "scenario_map":_scenario_map, "infographic":_infographic, "visual_metaphor":lambda:_title()+[_s("visual","隐喻主图",60,105,600,395),_s("callout","解释",700,155,240,250)],
}


def build_blueprint(family: str) -> list[Shape]:
    factory = FACTORIES.get(family)
    if factory is None:
        raise ValueError(f"缺少版式蓝图：{family}")
    return factory()
