from __future__ import annotations

import unittest

from ppt_system.generation.generation_prompts import build_reference_prompt_by_mode


class ReferencePromptShapeConstraintsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.page = {
            "page_no": 1,
            "title": "数据流与鲁棒性",
            "summary": "说明请求链路、状态闭环与存储导出之间的关系。",
            "bullets": ["输入调用区", "AI中心任务状态", "存储导出区"],
            "layout_family": "hub_and_spoke",
            "layout_slots": ["左侧输入区", "中部状态区", "右侧导出区"],
        }

    def test_compact_prompt_does_not_add_dashed_lines_when_style_has_no_dashed_hint(self) -> None:
        prompt = build_reference_prompt_by_mode(
            self.page,
            "蓝白科技汇报",
            2048,
            1152,
            prompt_mode="compact",
            style_guide={
                "style_core": {
                    "line_style": "蓝色实线连接器",
                }
            },
            has_reference_images=False,
            reference_style_adherence="balanced",
        )

        self.assertIn("不要主动增加虚线装饰", prompt)
        self.assertIn("相邻模块留出可识别间隔", prompt)

    def test_slot_brief_prompt_preserves_dashed_lines_when_style_requires(self) -> None:
        prompt = build_reference_prompt_by_mode(
            self.page,
            "蓝白科技汇报",
            2048,
            1152,
            prompt_mode="slot_brief",
            style_guide={
                "style_core": {
                    "line_style": "蓝色箭头与虚线连接器",
                },
                "element_primitives": ["虚线箭头连接器", "圆角信息卡片"],
            },
            has_reference_images=True,
            reference_style_adherence="strict",
        )

        self.assertIn("连接线按参考风格处理", prompt)
        self.assertIn("箭头关系清楚", prompt)
        self.assertIn("严格锁定原稿图的版芯比例", prompt)

    def test_baseline_prompt_discourages_soft_edges_and_blurry_borders(self) -> None:
        prompt = build_reference_prompt_by_mode(
            self.page,
            "蓝白科技汇报",
            2048,
            1152,
            prompt_mode="baseline",
            style_guide={
                "style_core": {
                    "line_style": "蓝色实线连接器",
                }
            },
            has_reference_images=False,
            reference_style_adherence="balanced",
        )

        self.assertIn("避免糊边、弱阴影、发光粘背景", prompt)
        self.assertIn("元素外沿不融入背景", prompt)

    def test_shape_constraints_do_not_recommend_card_or_border_as_default_design(self) -> None:
        prompt = build_reference_prompt_by_mode(
            self.page,
            "蓝白科技汇报",
            2048,
            1152,
            prompt_mode="compact",
            style_guide={},
            has_reference_images=False,
            reference_style_adherence="balanced",
        )

        self.assertIn("元素边界清楚", prompt)
        self.assertIn("相邻模块留出可识别间隔", prompt)
        self.assertNotIn("优先使用闭合且清晰的卡片", prompt)
        self.assertNotIn("关键箭头优先使用清晰实线", prompt)
        self.assertNotIn("整页都做成厚重硬框", prompt)

    def test_loose_slot_brief_prompt_keeps_creative_freedom(self) -> None:
        prompt = build_reference_prompt_by_mode(
            self.page,
            "蓝白科技汇报",
            2048,
            1152,
            prompt_mode="slot_brief",
            style_guide={
                "style_core": {
                    "line_style": "蓝色实线连接器",
                }
            },
            has_reference_images=True,
            reference_style_adherence="loose",
        )

        self.assertIn("优先学习原稿图的版芯比例", prompt)
        self.assertIn("你可以自主决定最适合的视觉重心", prompt)

    def test_no_reference_default_prompt_does_not_force_business_or_consulting_style(self) -> None:
        blocked_terms = ["企业", "商务", "咨询", "科技风格", "成熟企业"]

        prompts = [
            build_reference_prompt_by_mode(
                self.page,
                "",
                2048,
                1152,
                prompt_mode=mode,
                style_guide={},
                has_reference_images=False,
                reference_style_adherence="balanced",
            )
            for mode in ("baseline", "compact", "slot_brief")
        ]

        for prompt in prompts:
            self.assertIn("页面主题", prompt)
            for term in blocked_terms:
                self.assertNotIn(term, prompt)

    def test_no_reference_prompt_keeps_explicit_style_notes_as_user_context(self) -> None:
        prompt = build_reference_prompt_by_mode(
            self.page,
            "儿童科普手绘风",
            2048,
            1152,
            prompt_mode="compact",
            style_guide={},
            has_reference_images=False,
            reference_style_adherence="balanced",
        )

        self.assertIn("儿童科普手绘风", prompt)
        self.assertIn("优先服从已给定的风格说明", prompt)

    def test_all_prompt_modes_render_layout_family_in_chinese(self) -> None:
        for mode in ("baseline", "compact", "slot_brief"):
            prompt = build_reference_prompt_by_mode(
                self.page,
                "蓝白科技汇报",
                2048,
                1152,
                prompt_mode=mode,
                style_guide={"layout_families": ["hub_and_spoke", "process_horizontal"]},
                has_reference_images=True,
                reference_style_adherence="strict",
            )

            self.assertIn("中心辐射", prompt)
            self.assertNotIn("hub_and_spoke", prompt)
            self.assertNotIn("process_horizontal", prompt)

if __name__ == "__main__":
    unittest.main()
