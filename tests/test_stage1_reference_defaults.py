from __future__ import annotations

import unittest

from ppt_system.generation.content_agent import fallback_style_guide, normalize_content_plan


class Stage1ReferenceDefaultsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.style_guide = fallback_style_guide("蓝白科技汇报", has_reference_images=True)
        self.result = {
            "style_type": "商务汇报",
            "pages": [
                {
                    "page_no": 1,
                    "title": "AI学习的本质",
                    "summary": "对比搜索模式与检索型对话，并建立 AI 信息雷达。",
                    "bullets": ["搜索切换", "结构化提炼", "建立信息雷达"],
                    "layout_family": "split_top_bottom",
                    "layout_slots": ["顶部观点区", "中部对比区", "底部行动区"],
                    "image_prompt": "这是规划器返回的长 prompt，应在固定新策略下被忽略。",
                },
                {
                    "page_no": 2,
                    "title": "进阶玩法",
                    "summary": "展示流程图与模型选型的进阶用法。",
                    "bullets": ["流程图", "模型选型"],
                    "layout_family": "grid_n_x_m",
                    "layout_slots": ["标题区", "卡片区"],
                },
            ],
        }

    def test_reference_images_force_slot_brief_and_edit_mode(self) -> None:
        plan = normalize_content_plan(
            self.result,
            content="AI 学习与进阶玩法",
            page_count=2,
            image_width=2048,
            image_height=1152,
            style_notes="蓝白科技汇报",
            style_guide=self.style_guide,
            has_reference_images=True,
            generation_options={"include_cover_page": False, "reference_style_adherence": "strict"},
        )

        self.assertEqual(plan["pages"][0]["reference_mode"], "edit_with_refs")
        self.assertEqual(plan["pages"][1]["reference_mode"], "edit_with_refs")
        self.assertIn("语义分区", plan["pages"][0]["image_prompt"])
        self.assertIn("严格锁定原稿图的版芯比例", plan["pages"][0]["image_prompt"])
        self.assertNotIn("这是规划器返回的长 prompt", plan["pages"][0]["image_prompt"])

    def test_no_reference_images_use_compact_generation_prompt(self) -> None:
        plan = normalize_content_plan(
            self.result,
            content="AI 学习与进阶玩法",
            page_count=2,
            image_width=2048,
            image_height=1152,
            style_notes="蓝白科技汇报",
            style_guide=self.style_guide,
            has_reference_images=False,
            generation_options={"include_cover_page": False, "reference_style_adherence": "loose"},
        )

        self.assertEqual(plan["pages"][0]["reference_mode"], "generation")
        self.assertEqual(plan["pages"][1]["reference_mode"], "generation")
        self.assertIn("统一框架下调整", plan["pages"][0]["image_prompt"])

    def test_empty_style_notes_do_not_leak_inferred_business_style_into_prompt(self) -> None:
        result = {
            "style_type": "商务汇报",
            "pages": [
                {
                    "page_no": 1,
                    "title": "儿童节气观察",
                    "summary": "用自然观察活动解释四季节气变化。",
                    "bullets": ["观察天气", "记录植物", "分享发现"],
                    "layout_family": "grid_n_x_m",
                    "layout_slots": ["观察区", "记录区", "分享区"],
                }
            ],
        }

        plan = normalize_content_plan(
            result,
            content="面向小学生的节气观察活动",
            page_count=1,
            image_width=2048,
            image_height=1152,
            style_notes="",
            style_guide={},
            has_reference_images=False,
            generation_options={"include_cover_page": False},
        )

        prompt = plan["pages"][0]["image_prompt"]
        self.assertEqual(plan["style_type"], "商务汇报")
        self.assertIn("儿童节气观察", prompt)
        self.assertIn("不要套用固定领域模板", prompt)
        self.assertNotIn("商务汇报", prompt)
        self.assertNotIn("企业", prompt)
        self.assertNotIn("咨询", prompt)

    def test_no_reference_fallback_style_is_not_card_or_border_first(self) -> None:
        style_guide = fallback_style_guide("", has_reference_images=False)

        anchor = style_guide["prompt_anchor"]
        primitives = style_guide["element_primitives"]

        self.assertIn("信息分组方式随内容语义选择", anchor)
        self.assertIn("语义分组", primitives)
        self.assertIn("关系连接", primitives)
        self.assertNotIn("圆角", anchor)
        self.assertNotIn("描边", anchor)
        self.assertNotIn("rounded_card", primitives)
        self.assertNotIn("dashed_feedback_line", primitives)

    def test_reference_fallback_can_still_preserve_card_language_from_reference_images(self) -> None:
        style_guide = fallback_style_guide("蓝白科技汇报", has_reference_images=True)

        self.assertIn("卡片样式", style_guide["prompt_anchor"])
        self.assertIn("继承原稿图卡片描边与圆角", style_guide["style_core"]["card_style"])


if __name__ == "__main__":
    unittest.main()
