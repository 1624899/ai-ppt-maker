from __future__ import annotations

import unittest

from ppt_system.generation.planning_state import has_complete_page_plan, has_complete_planning_state


class PlanningStateTests(unittest.TestCase):
    def test_placeholder_pages_are_not_treated_as_complete_plan(self) -> None:
        state = {
            "job_meta": {"page_count": 2},
            "pages": [
                {
                    "page_no": 1,
                    "title": "第 1 页生成中",
                    "reference_prompt": "",
                },
                {
                    "page_no": 2,
                    "title": "第 2 页生成中",
                    "reference_prompt": "",
                },
            ],
        }

        self.assertFalse(has_complete_planning_state(state))

    def test_complete_pages_with_reference_prompts_are_resumable(self) -> None:
        state = {
            "job_meta": {"page_count": 2},
            "pages": [
                {
                    "page_no": 1,
                    "title": "封面",
                    "reference_prompt": "第一页原稿图提示词",
                },
                {
                    "page_no": 2,
                    "title": "流程页",
                    "reference_prompt": "第二页原稿图提示词",
                },
            ],
        }

        self.assertTrue(has_complete_planning_state(state))

    def test_page_count_mismatch_breaks_resume_readiness(self) -> None:
        pages = [
            {
                "page_no": 1,
                "reference_prompt": "第一页原稿图提示词",
            }
        ]

        self.assertFalse(has_complete_page_plan(pages, expected_count=2))


if __name__ == "__main__":
    unittest.main()
