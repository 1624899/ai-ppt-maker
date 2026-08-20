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


if __name__ == "__main__":
    unittest.main()
