from __future__ import annotations

import unittest

from ppt_system.generation.content_agent import build_planning_prompt, fallback_style_guide, normalize_content_plan
from ppt_system.generation.generation_options import resolve_generation_options
from ppt_system.generation.page_richness import resolve_page_richness_map


class PageRichnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.style_guide = fallback_style_guide("蓝白科技汇报", has_reference_images=True)

    def test_resolve_generation_options_supports_default_and_per_page_map(self) -> None:
        options = resolve_generation_options(
            {
                "page_count": "3",
                "page_richness_default": "high",
                "page_richness_map": {"1": "low", "2": "medium", "3": "high"},
                "reference_style_adherence": "strict",
            }
        )

        self.assertEqual(options["page_richness_default"], "high")
        self.assertEqual(options["page_richness_map"], {"1": "low", "2": "medium", "3": "high"})
        self.assertEqual(options["reference_style_adherence"], "strict")

    def test_normalize_content_plan_applies_per_page_richness(self) -> None:
        result = {
            "pages": [
                {
                    "page_no": 1,
                    "title": "总览",
                    "summary": "突出一个核心结论",
                    "bullets": ["结论", "背景"],
                    "layout_family": "hero_with_supporting_cards",
                },
                {
                    "page_no": 2,
                    "title": "拆解",
                    "summary": "展示更多模块关系",
                    "bullets": ["模块A", "模块B", "模块C"],
                    "layout_family": "grid_n_x_m",
                },
            ]
        }

        plan = normalize_content_plan(
            result,
            content="总览和拆解",
            page_count=2,
            image_width=2048,
            image_height=1152,
            style_notes="蓝白科技汇报",
            style_guide=self.style_guide,
            has_reference_images=True,
            generation_options={
                "include_cover_page": False,
                "page_richness_default": "medium",
                "page_richness_map": {"1": "low", "2": "high"},
                "reference_style_adherence": "balanced",
            },
        )

        self.assertEqual(plan["pages"][0]["page_richness"], "low")
        self.assertEqual(plan["pages"][1]["page_richness"], "high")
        self.assertIn("信息密度偏低", plan["pages"][0]["style_constraints"])
        self.assertIn("信息密度偏高", plan["pages"][1]["style_constraints"])
        self.assertIn("控制视觉元素与文字块数量", plan["pages"][0]["image_prompt"])
        self.assertIn("允许出现更多卡片、节点、图表分区或说明标签", plan["pages"][1]["image_prompt"])

    def test_build_planning_prompt_contains_page_richness_requirements(self) -> None:
        richness_map = resolve_page_richness_map(
            page_count=3,
            default_level="medium",
            explicit_map={"1": "low", "2": "high"},
        )
        prompt = build_planning_prompt(
            content="A\nB\nC",
            page_count=3,
            image_width=2048,
            image_height=1152,
            style_notes="蓝白科技汇报",
            style_image_count=1,
            style_guide=self.style_guide,
            generation_options={
                "include_cover_page": True,
                "page_richness_default": "medium",
                "reference_style_adherence": "strict",
            },
            page_richness_map=richness_map,
        )

        self.assertIn("第 1 页：丰富度低", prompt)
        self.assertIn("第 2 页：丰富度高", prompt)
        self.assertIn('"page_richness": "low/medium/high 之一"', prompt)
        self.assertIn("参考图约束强度：严格", prompt)
        self.assertIn("把参考图当成强约束模板", prompt)


if __name__ == "__main__":
    unittest.main()
