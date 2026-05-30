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

    def test_compact_prompt_reduces_dashed_lines_when_style_has_no_dashed_hint(self) -> None:
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

        self.assertIn("尽量少用虚线", prompt)
        self.assertIn("元素边际线要明确", prompt)

    def test_slot_brief_prompt_allows_small_amount_of_dashed_lines_when_style_requires(self) -> None:
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

        self.assertIn("可以保留少量虚线连接器", prompt)
        self.assertIn("关键箭头优先使用清晰实线或明确描边", prompt)
        self.assertIn("严格锁定参考图的版芯比例", prompt)

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

        self.assertIn("不要用模糊发光、弱对比阴影或糊边代替描边", prompt)
        self.assertIn("少生成边界发虚、边缘融入背景", prompt)

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

        self.assertIn("优先学习参考图的版芯比例", prompt)
        self.assertIn("你可以自主决定最适合的视觉重心", prompt)


if __name__ == "__main__":
    unittest.main()
