from __future__ import annotations

import unittest

from ppt_system.web.services.plan_version_store import apply_plan_to_state


class PlanPromptSyncTests(unittest.TestCase):
    def _state(self) -> dict:
        return {
            "job_meta": {
                "page_count": 2,
                "style_notes": "清爽蓝白科技风",
                "image_preset": {"width": 2048, "height": 1152},
                "generation_options": {"reference_style_adherence": "balanced"},
                "style_reference_images": [],
            },
            "plan": {
                "style_guide": {
                    "style_core": {"line_style": "蓝色实线连接器"},
                    "element_primitives": ["圆角卡片", "箭头连接器"],
                },
            },
            "pages": [
                {
                    "page_no": 1,
                    "title": "旧标题",
                    "summary": "旧摘要",
                    "reference_prompt": "旧原稿图提示词",
                    "elements_prompt": "旧元素图提示词",
                },
                {
                    "page_no": 2,
                    "title": "手动页",
                    "summary": "保持用户手写提示词",
                    "reference_prompt": "用户手写原稿图提示词",
                    "elements_prompt": "用户手写元素图提示词",
                },
            ],
            "reference_pages": [],
            "element_pages": [],
        }

    def test_stale_prompts_are_rebuilt_from_current_page_content(self) -> None:
        state = self._state()

        apply_plan_to_state(
            state,
            {
                "title": "测试规划",
                "style_notes": "清爽蓝白科技风",
                "pages": [
                    {
                        "page_no": 1,
                        "title": "新标题",
                        "summary": "新摘要",
                        "bullets": ["新要点一", "新要点二"],
                        "layout_family": "process_horizontal",
                        "visual_suggestion": "使用清晰流程箭头",
                        "reference_prompt": "旧原稿图提示词",
                        "elements_prompt": "旧元素图提示词",
                        "reference_prompt_stale": True,
                        "elements_prompt_stale": True,
                    }
                ],
            },
        )

        page = state["pages"][0]
        self.assertIn("新标题", page["reference_prompt"])
        self.assertIn("新要点一", page["reference_prompt"])
        self.assertIn("使用清晰流程箭头", page["reference_prompt"])
        self.assertNotEqual("旧原稿图提示词", page["reference_prompt"])
        self.assertNotEqual("旧元素图提示词", page["elements_prompt"])
        self.assertFalse(page["reference_prompt_stale"])
        self.assertFalse(page["elements_prompt_stale"])

    def test_manual_prompts_are_preserved_when_content_changes(self) -> None:
        state = self._state()

        apply_plan_to_state(
            state,
            {
                "title": "测试规划",
                "pages": [
                    {
                        "page_no": 2,
                        "title": "用户改过内容",
                        "summary": "但希望保留手写提示词",
                        "layout_family": "hub_and_spoke",
                        "reference_prompt": "用户手写原稿图提示词",
                        "elements_prompt": "用户手写元素图提示词",
                        "reference_prompt_manual": True,
                        "elements_prompt_manual": True,
                        "reference_prompt_stale": False,
                        "elements_prompt_stale": False,
                    }
                ],
            },
        )

        page = state["pages"][0]
        self.assertEqual("用户手写原稿图提示词", page["reference_prompt"])
        self.assertEqual("用户手写元素图提示词", page["elements_prompt"])


if __name__ == "__main__":
    unittest.main()
