from __future__ import annotations

import unittest

from ppt_system.generation.design_grammar import DEFAULT_LAYOUT_FAMILIES
from ppt_system.generation.layout_intent import infer_layout_intent
from ppt_system.generation.layout_profiles import LAYOUT_PROFILES
from ppt_system.generation.layout_recommender import recommend_layout_candidates


class LayoutProfilesTests(unittest.TestCase):
    def test_all_registered_layouts_have_complete_profiles(self) -> None:
        self.assertEqual(set(DEFAULT_LAYOUT_FAMILIES), set(LAYOUT_PROFILES))
        for profile in LAYOUT_PROFILES.values():
            self.assertTrue(profile.category)
            self.assertTrue(profile.description)
            self.assertTrue(profile.semantic_group)
            self.assertTrue(profile.visual_axis)

    def test_intent_and_candidates_explain_comparison_content(self) -> None:
        intent = infer_layout_intent("方案对比", "比较两个方案的关键指标", ["成本", "效率", "风险"], include_cover_page=False)
        candidates = recommend_layout_candidates("方案对比", "比较两个方案的关键指标", ["成本", "效率", "风险"], include_cover_page=False)
        self.assertEqual(intent.intent, "comparison")
        self.assertEqual(candidates[0]["value"], "compare_dual_axis")
        self.assertIn("content_fit", candidates[0]["reason"])

    def test_candidates_are_always_filled_to_five_and_sorted_by_score(self) -> None:
        candidates = recommend_layout_candidates(
            "单一候选也需要替代版式",
            "根据内容匹配程度展示候选",
            ["核心观点", "辅助说明"],
            candidate_families=["split_left_right"],
            include_cover_page=False,
        )

        self.assertEqual(len(candidates), 5)
        self.assertEqual(
            [item["score"] for item in candidates],
            sorted((item["score"] for item in candidates), reverse=True),
        )

    def test_candidates_remain_exactly_five_with_a_small_preferred_pool(self) -> None:
        candidates = recommend_layout_candidates(
            "项目推进",
            "按阶段完成交付",
            ["准备", "执行", "验收"],
            candidate_families=["process_horizontal", "timeline_horizontal", "swimlane"],
            include_cover_page=False,
        )

        self.assertEqual(len(candidates), 5)
        self.assertEqual(len({item["value"] for item in candidates}), 5)


if __name__ == "__main__":
    unittest.main()
