from __future__ import annotations

import unittest

from ppt_system.generation.content_agent import (
    build_planning_prompt,
    fallback_style_guide,
    normalize_content_plan,
)


class LayoutPromptConstraintsTests(unittest.TestCase):
    def test_fallback_style_guide_without_reference_images_does_not_require_pages(self) -> None:
        style_guide = fallback_style_guide("清晰简洁", False)

        self.assertEqual(style_guide["style_name"], "清晰简洁")

    def test_normalized_pages_share_generated_layout_report(self) -> None:
        plan = normalize_content_plan(
            {"pages": [{"title": "项目概览"}, {"title": "实施路径"}]},
            content="介绍项目背景、实施路径和预期价值。",
            page_count=2,
            image_width=2048,
            image_height=1152,
            style_notes="清晰简洁",
            style_guide=fallback_style_guide("清晰简洁", False),
            has_reference_images=False,
        )

        self.assertEqual(plan["layout_report"], plan["pages"][0]["layout_report"])
        self.assertEqual(plan["layout_report"], plan["pages"][1]["layout_report"])

    def test_locked_layout_is_preserved_across_adjacent_pages(self) -> None:
        plan = normalize_content_plan(
            {
                "pages": [
                    {"title": "核心人物", "layout_family": "people_profile", "layout_locked": True},
                    {"title": "项目负责人", "layout_family": "people_profile", "layout_locked": True},
                ]
            },
            content="介绍项目核心人物和项目负责人。",
            page_count=2,
            image_width=2048,
            image_height=1152,
            style_notes="清晰简洁",
            style_guide=fallback_style_guide("清晰简洁", False),
            has_reference_images=False,
        )

        self.assertEqual([page["layout_family"] for page in plan["pages"]], ["people_profile", "people_profile"])

    def test_single_page_does_not_run_deck_layout_optimization(self) -> None:
        plan = normalize_content_plan(
            {"pages": [{"title": "核心人物", "layout_family": "people_profile"}]},
            content="介绍项目核心人物。",
            page_count=1,
            image_width=2048,
            image_height=1152,
            style_notes="清晰简洁",
            style_guide=fallback_style_guide("清晰简洁", False),
            has_reference_images=False,
        )

        self.assertEqual(plan["pages"][0]["layout_family"], "people_profile")

    def test_initial_valid_layout_is_preserved_without_lock(self) -> None:
        plan = normalize_content_plan(
            {"pages": [
                {"title": "核心人物", "layout_family": "people_profile"},
                {"title": "项目负责人", "layout_family": "people_profile"},
            ]},
            content="介绍项目核心人物和项目负责人。",
            page_count=2,
            image_width=2048,
            image_height=1152,
            style_notes="清晰简洁",
            style_guide=fallback_style_guide("清晰简洁", False),
            has_reference_images=False,
        )

        self.assertEqual([page["layout_family"] for page in plan["pages"]], ["people_profile", "people_profile"])

    def test_user_confirmed_layout_metadata_is_preserved(self) -> None:
        plan = normalize_content_plan(
            {"pages": [{
                "title": "空间规划",
                "layout_family": "floor_plan",
                "layout_locked": True,
                "layout_user_confirmed": True,
                "layout_source": "user",
            }]},
            content="展示空间规划。",
            page_count=1,
            image_width=2048,
            image_height=1152,
            style_notes="清晰简洁",
            style_guide=fallback_style_guide("清晰简洁", False),
            has_reference_images=False,
        )

        page = plan["pages"][0]
        self.assertEqual(page["layout_family"], "floor_plan")
        self.assertTrue(page["layout_locked"])
        self.assertTrue(page["layout_user_confirmed"])
        self.assertEqual(page["layout_source"], "user")

    def test_planning_prompt_uses_closed_layout_enum_and_chinese_human_text(self) -> None:
        prompt = build_planning_prompt(
            content="介绍产品定位、实施步骤与方案价值。",
            page_count=3,
            image_width=2048,
            image_height=1152,
            style_notes="清晰简洁",
            style_image_count=0,
            style_guide=fallback_style_guide("清晰简洁", False),
        )

        self.assertIn("layout_family 是封闭枚举", prompt)
        self.assertIn('"process_horizontal"（横向流程）', prompt)
        self.assertIn("禁止自造、翻译、拼接或添加后缀", prompt)
        self.assertIn("layout_slots 必须与所选 layout_family 的结构一致", prompt)
        self.assertIn("所有面向人的文本字段必须使用中文", prompt)
        self.assertNotIn('"layout_family": "从可用版式家族中选择一个抽象排版模式"', prompt)


if __name__ == "__main__":
    unittest.main()
