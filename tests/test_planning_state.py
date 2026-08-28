from __future__ import annotations

import unittest

from ppt_system.generation.planning_state import has_complete_page_plan, has_complete_planning_state
from ppt_system.web.services.plan_version_store import build_plan_response, save_plan_version
from ppt_system.web.services.planning_state import build_planned_runtime_pages


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

    def test_layout_recommendations_survive_runtime_and_version_storage(self) -> None:
        candidates = [
            {"value": f"layout_{index}", "score": 100 - index, "reason": {"content_fit": f"理由{index}"}}
            for index in range(5)
        ]
        source_page = {
            "page_no": 1,
            "title": "版式推荐测试",
            "summary": "验证规划状态完整保存推荐数据。",
            "bullets": ["候选生成", "状态写入", "版本保存"],
            "layout_intent": {"intent": "summary", "density": "medium"},
            "layout_family": "layout_0",
            "layout_reason": "当前版式最符合页面内容。",
            "layout_recommendation": candidates[0],
            "layout_candidates": candidates,
            "layout_source": "ai",
            "layout_locked": False,
            "layout_user_confirmed": False,
            "visual_suggestion": "使用流程图突出状态流转。",
            "style_constraints": "保持蓝白科技风格。",
            "source_anchor_ids": ["source-1"],
            "chart_data": {"type": "bar", "values": [1, 2]},
        }

        runtime_pages = build_planned_runtime_pages([source_page])
        state = {
            "job_id": "test-job",
            "job_meta": {"page_count": 1, "title": "版式推荐测试"},
            "plan": {"title": "版式推荐测试", "pages": [source_page]},
            "pages": runtime_pages,
        }
        save_plan_version(state, source="model", summary="模型初始规划")
        response_page = build_plan_response(state)["plan"]["pages"][0]
        version_page = state["plan_versions"][0]["plan"]["pages"][0]

        self.assertEqual(len(runtime_pages[0]["layout_candidates"]), 5)
        self.assertEqual(len(response_page["layout_candidates"]), 5)
        self.assertEqual(len(version_page["layout_candidates"]), 5)
        self.assertEqual(response_page["layout_recommendation"]["value"], "layout_0")
        self.assertEqual(response_page["layout_reason"], "当前版式最符合页面内容。")
        self.assertEqual(response_page["layout_source"], "ai")
        self.assertEqual(runtime_pages[0]["visual_suggestion"], "使用流程图突出状态流转。")
        self.assertEqual(response_page["style_constraints"], "使用流程图突出状态流转。")
        self.assertEqual(runtime_pages[0]["source_anchor_ids"], ["source-1"])
        self.assertEqual(version_page["chart_data"], {"type": "bar", "values": [1, 2]})


if __name__ == "__main__":
    unittest.main()
