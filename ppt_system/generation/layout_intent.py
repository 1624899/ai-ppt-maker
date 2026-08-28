from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Sequence

from ppt_system.generation.page_richness import normalize_page_richness_level


@dataclass(frozen=True)
class LayoutIntent:
    intent: str
    content_role: str
    density: str
    item_count: int
    has_metrics: bool
    has_time_sequence: bool
    has_process: bool
    has_relationship: bool
    has_image_focus: bool
    visual_priority: str
    metric_count: int
    comparison_object_count: int
    dimension_count: int
    matched_signals: tuple[str, ...]

    def to_dict(self) -> dict:
        result = asdict(self)
        result["matched_signals"] = list(self.matched_signals)
        return result


def infer_layout_intent(title: str, summary: str, bullets: Sequence[str], *, page_richness: str = "medium", page_index: int = 0, include_cover_page: bool = True) -> LayoutIntent:
    text = f"{title} {summary} {' '.join(str(item) for item in bullets)}".lower()
    count = len([item for item in bullets if str(item).strip()])
    signals: list[str] = []
    def found(words: tuple[str, ...], label: str) -> bool:
        if any(word in text for word in words): signals.append(label); return True
        return False
    numeric_values = re.findall(r"\d+(?:\.\d+)?[%％]?", text)
    metrics = found(("指标", "数据", "同比", "环比", "增长", "金额", "%", "趋势"), "关键指标") or bool(numeric_values)
    timeline = found(("时间线", "时间轴", "历程", "里程碑", "发展阶段", "演进"), "时间顺序")
    process = found(("流程", "步骤", "环节", "执行", "推进"), "步骤关系")
    relation = found(("关系", "体系", "架构", "层级", "生态", "协同", "平台", "核心功能", "能力体系", "功能模块"), "结构关系")
    comparison = found(("对比", "比较", "差异", "优劣", "vs", "对照"), "对比对象")
    image_focus = found(("产品", "人物", "案例", "场景", "品牌", "主视觉"), "主视觉对象")
    platform_structure = any(word in text for word in ("平台", "核心功能", "功能模块", "能力体系"))
    primary_text = f"{title} {summary}".lower()
    explicit_process = (
        any(word in text for word in ("→", "->", "=>", "输入到输出"))
        or any(word in primary_text for word in ("流程", "步骤", "环节"))
    )
    if include_cover_page and page_index == 0: intent, role = "cover", "opening"
    elif comparison: intent, role = "comparison", "evidence"
    elif process and (explicit_process or not platform_structure): intent, role = "process", "method"
    elif timeline: intent, role = "timeline", "context"
    elif relation: intent, role = "relationship", "framework"
    elif metrics: intent, role = "data_analysis", "evidence"
    elif image_focus: intent, role = "product_showcase", "example"
    elif found(("总结", "结论", "复盘", "成果"), "结论内容"): intent, role = "summary", "closing"
    elif found(("计划", "目标", "行动", "策略"), "行动安排"): intent, role = "action_plan", "action"
    else: intent, role = "key_message", "narrative"
    density = normalize_page_richness_level(page_richness)
    comparison_objects = 2 if comparison else 0
    dimensions = count if comparison else 0
    return LayoutIntent(intent, role, density, count, metrics, timeline, process, relation, image_focus,
        "high" if image_focus or intent in {"cover", "product_showcase"} else "medium", len(numeric_values), comparison_objects, dimensions, tuple(signals))
