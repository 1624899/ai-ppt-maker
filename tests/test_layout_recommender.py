from __future__ import annotations

import unittest

from ppt_system.generation.layout_recommender import choose_layout_family, recommend_layout_family
from ppt_system.generation.text_layout import build_layout_slots_by_family


class LayoutRecommenderTests(unittest.TestCase):
    def test_recommends_specialized_layouts_from_content_relationships(self) -> None:
        cases = [
            ("销售转化漏斗", "从获客到成交", ["访问", "线索", "成交"], "high", "funnel"),
            ("项目排期", "甘特图展示开始时间和完成时间", ["需求", "开发", "上线"], "high", "gantt_chart"),
            ("跨部门审批", "泳道图明确责任人与角色分工", ["业务", "法务", "财务", "管理层"], "high", "swimlane"),
            ("核心人物介绍", "创始人个人简介和履历", ["教育背景", "工作经历"], "low", "people_profile"),
            ("经营看板", "仪表盘展示综合指标", ["收入", "利润", "客户", "转化", "成本"], "high", "dashboard"),
            ("智能化项目平台", "1个平台承载4个核心功能", ["统一入口", "数据分析", "流程协同", "权限管理"], "high", "hub_and_spoke"),
        ]

        for title, summary, bullets, richness, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(
                    recommend_layout_family(
                        title,
                        summary,
                        bullets,
                        page_richness=richness,
                        include_cover_page=False,
                    ),
                    expected,
                )

    def test_reference_candidates_limit_recommendation_scope(self) -> None:
        family = recommend_layout_family(
            "销售转化漏斗",
            "从获客到成交",
            ["访问", "线索", "成交"],
            candidate_families=["process_horizontal", "timeline_horizontal"],
            include_cover_page=False,
        )

        self.assertEqual(family, "process_horizontal")

    def test_obviously_mismatched_ai_suggestion_is_corrected(self) -> None:
        family = choose_layout_family(
            "people_profile",
            "年度销售趋势",
            "折线展示连续月份的增长走势",
            ["一季度", "二季度", "三季度", "四季度"],
            page_richness="medium",
            include_cover_page=False,
        )

        self.assertEqual(family, "line_chart")

    def test_reasonable_ai_suggestion_is_preserved(self) -> None:
        family = choose_layout_family(
            "process_horizontal",
            "实施步骤",
            "分阶段完成方案落地",
            ["准备", "执行", "验收"],
            page_richness="medium",
            include_cover_page=False,
        )

        self.assertEqual(family, "process_horizontal")

    def test_content_density_changes_slot_height(self) -> None:
        low = build_layout_slots_by_family("process_horizontal", 2048, 1152, "low")
        high = build_layout_slots_by_family("process_horizontal", 2048, 1152, "high")

        self.assertLess(low["slot_coords"]["step_1"][3], high["slot_coords"]["step_1"][3])


if __name__ == "__main__":
    unittest.main()
