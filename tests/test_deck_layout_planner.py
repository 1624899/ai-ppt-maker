from __future__ import annotations

import unittest

from ppt_system.generation.deck_layout_planner import plan_deck_layouts


class DeckLayoutPlannerTests(unittest.TestCase):
    def test_avoids_adjacent_semantic_and_visual_repetition(self) -> None:
        pages = [
            [{"value": "grid_n_x_m", "score": 100}, {"value": "line_chart", "score": 80}],
            [{"value": "module_combination", "score": 100}, {"value": "line_chart", "score": 80}],
        ]
        selected = plan_deck_layouts(pages)
        self.assertEqual([item["value"] for item in selected], ["grid_n_x_m", "line_chart"])

    def test_locked_layout_is_preserved(self) -> None:
        pages = [[{"value": "grid_n_x_m", "score": 10}, {"value": "line_chart", "score": 100}]]
        selected = plan_deck_layouts(pages, locked_families=["grid_n_x_m"])
        self.assertEqual(selected[0]["value"], "grid_n_x_m")


if __name__ == "__main__":
    unittest.main()
