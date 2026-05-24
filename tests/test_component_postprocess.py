from __future__ import annotations

import unittest

import numpy as np

from ppt_system.component_postprocess import absorb_overlapping_fragments


def _component(left: int, top: int, width: int, height: int, area: int) -> dict[str, object]:
    return {
        "left": left,
        "top": top,
        "right": left + width,
        "bottom": top + height,
        "area": area,
        "mask": np.ones((height, width), dtype=bool),
    }


class ComponentPostprocessTests(unittest.TestCase):
    def test_absorb_overlapping_fragments_merges_tiny_edge_fragment_into_large_component(self) -> None:
        components = [
            _component(0, 80, 100, 15, 1500),
            _component(90, 95, 8, 3, 12),
        ]

        merged = absorb_overlapping_fragments(
            components,
            image_width=100,
            image_height=100,
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(int(merged[0]["area"]), 1524)

    def test_absorb_overlapping_fragments_keeps_interior_small_component_separate(self) -> None:
        components = [
            _component(10, 10, 80, 80, 6400),
            _component(40, 40, 6, 6, 24),
        ]

        merged = absorb_overlapping_fragments(
            components,
            image_width=100,
            image_height=100,
        )

        self.assertEqual(len(merged), 2)


if __name__ == "__main__":
    unittest.main()
