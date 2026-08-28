from __future__ import annotations

import unittest

from ppt_system.generation.content_agent import (
    apply_planning_revision_guard,
    build_planning_prompt,
    build_planning_revision_prompt,
    fallback_style_guide,
    normalize_content_plan,
)


class LayoutPromptConstraintsTests(unittest.TestCase):
    def test_fallback_style_guide_without_reference_images_does_not_require_pages(self) -> None:
        style_guide = fallback_style_guide("清晰简洁", False)

        self.assertEqual(style_guide["style_name"], "清晰简洁")
        self.assertEqual(style_guide["negative_rules"], [])
        self.assertEqual(style_guide["constraint_sources"]["user"], "清晰简洁")
        self.assertEqual(style_guide["constraint_sources"]["reference"], "")

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

    def test_unlocked_ai_layout_must_be_in_recommended_candidates(self) -> None:
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

        self.assertEqual(plan["pages"][0]["layout_family"], "people_profile")
        self.assertNotEqual(plan["pages"][1]["layout_family"], "people_profile")
        self.assertIn(
            plan["pages"][1]["layout_family"],
            [item["value"] for item in plan["pages"][1]["layout_candidates"]],
        )

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

    def test_revision_guard_preserves_content_and_untouched_pages(self) -> None:
        previous_plan = {
            "narrative": "原始整套叙事",
            "pages": [
                {"page_no": 1, "title": "第一页", "summary": "原摘要", "bullets": ["事实A"], "layout_family": "grid_n_x_m"},
                {"page_no": 2, "title": "第二页", "summary": "原摘要2", "bullets": ["事实B"], "layout_family": "invented_layout"},
            ]
        }
        revised_plan = {
            "narrative": "被模型擅自改写的顶层叙事",
            "pages": [
                {"page_no": 1, "title": "被误改", "summary": "被误改", "bullets": ["虚构内容"], "layout_family": "dashboard"},
                {
                    "page_no": 2,
                    "title": "被误改2",
                    "summary": "被误改2",
                    "bullets": ["虚构内容2"],
                    "layout_family": "summary_detail",
                    "element_plan": {"primitives": ["被擅自修改的元素"]},
                    "image_prompt": "被擅自修改的提示词",
                },
            ]
        }
        feedback = {
            "findings": [{"code": "invalid_layout_family", "actionable": True, "page_no": 2}],
        }

        guarded = apply_planning_revision_guard(revised_plan, previous_plan, feedback)

        self.assertEqual(guarded["pages"][0], previous_plan["pages"][0])
        self.assertEqual(guarded["pages"][1]["title"], "第二页")
        self.assertEqual(guarded["pages"][1]["bullets"], ["事实B"])
        self.assertEqual(guarded["pages"][1]["layout_family"], "summary_detail")
        self.assertNotIn("element_plan", guarded["pages"][1])
        self.assertNotIn("image_prompt", guarded["pages"][1])
        self.assertEqual(guarded["narrative"], "原始整套叙事")

    def test_revision_prompt_only_exposes_actionable_findings(self) -> None:
        previous_plan = {
            "pages": [{"page_no": 1, "title": "原标题", "bullets": ["事实A"]}],
        }
        feedback = {
            "summary": "存在一项确定性错误和一项启发式警告",
            "findings": [
                {
                    "code": "invalid_layout_family",
                    "severity": "error",
                    "actionable": True,
                    "page_no": 1,
                    "message": "版式非法",
                    "evidence": {"source": "deterministic_rule"},
                },
                {
                    "code": "style_anchor_coverage",
                    "severity": "warning",
                    "actionable": False,
                    "page_no": 1,
                    "message": "关键词命中率较低",
                    "evidence": {"source": "heuristic"},
                },
            ],
        }

        prompt = build_planning_revision_prompt("基础规划要求", previous_plan, feedback)

        self.assertIn("previous_plan", prompt)
        self.assertIn("invalid_layout_family", prompt)
        self.assertNotIn("style_anchor_coverage", prompt)
        self.assertIn("已通过且没有 actionable 问题的页面必须保持", prompt)

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
