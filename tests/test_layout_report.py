from __future__ import annotations

import unittest

from ppt_system.generation.deck_layout_planner import build_deck_layout_report


class LayoutReportTests(unittest.TestCase):
    def test_report_scores_diversity_and_flags_repetition(self) -> None:
        report = build_deck_layout_report([
            {"value": "grid_n_x_m"},
            {"value": "module_combination"},
            {"value": "line_chart"},
        ])
        self.assertEqual(report["page_count"], 3)
        self.assertGreaterEqual(report["diversity_score"], 0)
        self.assertTrue(report["issues"])


if __name__ == "__main__":
    unittest.main()
