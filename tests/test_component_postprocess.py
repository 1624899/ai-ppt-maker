from __future__ import annotations

import unittest

import numpy as np

from ppt_system.component_postprocess import (
    absorb_overlapping_fragments,
    merge_dashed_line_components,
    merge_related_components,
)


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
    def test_merge_dashed_line_components_merges_horizontal_dash_cluster(self) -> None:
        components = [
            _component(10, 20, 10, 4, 40),
            _component(26, 20, 10, 4, 40),
            _component(42, 20, 10, 4, 40),
        ]

        merged = merge_dashed_line_components(
            components,
            image_width=200,
            image_height=100,
            max_dash_gap=12,
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(int(merged[0]["area"]), 120)

    def test_merge_dashed_line_components_does_not_merge_large_blocks(self) -> None:
        components = [
            _component(10, 10, 20, 20, 400),
            _component(34, 10, 20, 20, 400),
            _component(58, 10, 20, 20, 400),
        ]

        merged = merge_dashed_line_components(
            components,
            image_width=200,
            image_height=100,
            max_dash_gap=12,
        )

        self.assertEqual(len(merged), 3)

    def test_merge_related_components_keeps_meaningful_inner_fragment_separate(self) -> None:
        components = [
            _component(10, 10, 80, 80, 4200),
            _component(34, 34, 18, 18, 180),
        ]

        merged = merge_related_components(
            components,
            image_width=100,
            image_height=100,
            merge_distance=6,
        )

        self.assertEqual(len(merged), 2)

    def test_merge_related_components_keeps_two_nearby_fragment_components_separate(self) -> None:
        components = [
            _component(10, 10, 8, 8, 64),
            _component(22, 10, 8, 8, 64),
        ]

        merged = merge_related_components(
            components,
            image_width=100,
            image_height=100,
            merge_distance=6,
        )

        self.assertEqual(len(merged), 2)

    def test_merge_related_components_merges_compact_fragment_cluster(self) -> None:
        components = [
            _component(10, 10, 6, 6, 36),
            _component(19, 10, 6, 6, 36),
            _component(14, 18, 6, 6, 36),
        ]

        merged = merge_related_components(
            components,
            image_width=100,
            image_height=100,
            merge_distance=6,
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(int(merged[0]["area"]), 108)

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
