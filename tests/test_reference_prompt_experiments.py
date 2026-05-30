from __future__ import annotations

import unittest

from ppt_system.generation.reference_prompt_experiments import (
    build_prompt_experiment_case,
    list_prompt_experiment_strategies,
)


class ReferencePromptExperimentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.page = {
            "page_no": 1,
            "title": "AI学习的本质",
            "summary": "从搜索模式切换到检索型对话，并建立信息雷达。",
            "bullets": [
                "改变信息获取与处理方式",
                "从关键词搜索转向检索型对话",
                "建立 AI 信息雷达",
            ],
            "layout_family": "split_top_bottom",
            "layout_slots": [
                "顶部主标题与核心判断区",
                "中部左右对比区",
                "底部行动路径区",
            ],
            "image_prompt": "这是当前主流程里的长 prompt，用来作为实验基线。",
        }
        self.style_guide = {
            "prompt_anchor": "白底浅蓝科技纹理，深蓝标题，细描边卡片，咨询报告式信息图。",
            "style_core": {
                "background_tone": "高明度白底与极浅蓝背景",
                "palette": ["深海军蓝", "科技亮蓝", "风险红"],
                "title_style": "深蓝粗体标题",
                "card_style": "细描边圆角卡片",
            },
        }

    def test_all_strategies_are_exposed(self) -> None:
        strategy_ids = [item.strategy_id for item in list_prompt_experiment_strategies()]

        self.assertEqual(
            strategy_ids,
            [
                "baseline_generation",
                "baseline_edit_refs",
                "compact_generation",
                "compact_edit_refs",
                "slot_brief_edit_refs",
            ],
        )

    def test_baseline_prompt_reuses_existing_prompt(self) -> None:
        case = build_prompt_experiment_case(
            page=self.page,
            style_guide=self.style_guide,
            image_width=2048,
            image_height=1152,
            strategy_id="baseline_generation",
            style_reference_count=2,
        )

        self.assertEqual(case.prompt, self.page["image_prompt"])
        self.assertEqual(case.effective_reference_mode, "generation")
        self.assertFalse(case.uses_reference_images)

    def test_edit_strategy_falls_back_when_no_refs(self) -> None:
        case = build_prompt_experiment_case(
            page=self.page,
            style_guide=self.style_guide,
            image_width=2048,
            image_height=1152,
            strategy_id="baseline_edit_refs",
            style_reference_count=0,
        )

        self.assertEqual(case.requested_reference_mode, "edit_with_refs")
        self.assertEqual(case.effective_reference_mode, "generation")
        self.assertFalse(case.uses_reference_images)

    def test_compact_prompt_is_more_autonomous_than_baseline(self) -> None:
        case = build_prompt_experiment_case(
            page=self.page,
            style_guide=self.style_guide,
            image_width=2048,
            image_height=1152,
            strategy_id="compact_edit_refs",
            style_reference_count=2,
            reference_style_adherence="balanced",
        )

        self.assertIn("基准约束", case.prompt)
        self.assertIn("统一框架下调整", case.prompt)
        self.assertTrue(case.uses_reference_images)
        self.assertEqual(case.effective_reference_mode, "edit_with_refs")

    def test_slot_brief_prompt_uses_semantic_slots(self) -> None:
        case = build_prompt_experiment_case(
            page=self.page,
            style_guide=self.style_guide,
            image_width=2048,
            image_height=1152,
            strategy_id="slot_brief_edit_refs",
            style_reference_count=2,
            reference_style_adherence="strict",
        )

        self.assertIn("语义分区", case.prompt)
        self.assertIn("1. 顶部主标题与核心判断区", case.prompt)
        self.assertIn("严格锁定参考图的版芯比例", case.prompt)
        self.assertNotIn("x=", case.prompt)


if __name__ == "__main__":
    unittest.main()
