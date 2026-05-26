from __future__ import annotations

import unittest

from ppt_system.component_filter import filter_decorative_components


def _component(left: int, top: int, width: int, height: int, area: int) -> dict[str, object]:
    return {
        "left": left,
        "top": top,
        "right": left + width,
        "bottom": top + height,
        "area": area,
        "mask": [[True]],
    }


class ComponentFilterTests(unittest.TestCase):
    def test_filter_drops_tiny_compact_near_edge_fragment(self) -> None:
        kept, removed = filter_decorative_components(
            [_component(96, 40, 3, 3, 8)],
            image_width=100,
            image_height=100,
        )
        self.assertEqual(len(kept), 0)
        self.assertEqual(len(removed), 1)

    def test_filter_drops_sparse_edge_strip(self) -> None:
        kept, removed = filter_decorative_components(
            [_component(40, 95, 35, 5, 7)],
            image_width=100,
            image_height=100,
        )
        self.assertEqual(len(kept), 0)
        self.assertEqual(len(removed), 1)

    def test_filter_keeps_dense_edge_block(self) -> None:
        kept, removed = filter_decorative_components(
            [_component(85, 40, 15, 20, 220)],
            image_width=100,
            image_height=100,
        )
        self.assertEqual(len(kept), 1)
        self.assertEqual(len(removed), 0)

    def test_filter_drops_small_sparse_fragment_cluster_even_away_from_edge(self) -> None:
        component = _component(40, 40, 20, 10, 12)
        component["component_count"] = 4
        component["contains_anchor"] = False

        kept, removed = filter_decorative_components(
            [component],
            image_width=100,
            image_height=100,
        )

        self.assertEqual(len(kept), 0)
        self.assertEqual(len(removed), 1)

    def test_filter_keeps_dense_fragment_cluster_with_meaningful_area(self) -> None:
        component = _component(35, 35, 16, 16, 120)
        component["component_count"] = 4
        component["contains_anchor"] = False

        kept, removed = filter_decorative_components(
            [component],
            image_width=100,
            image_height=100,
        )

        self.assertEqual(len(kept), 1)
        self.assertEqual(len(removed), 0)

    def test_filter_drops_short_hairline_inside_canvas(self) -> None:
        kept, removed = filter_decorative_components(
            [_component(40, 40, 15, 1, 15)],
            image_width=100,
            image_height=100,
        )

        self.assertEqual(len(kept), 0)
        self.assertEqual(len(removed), 1)

    def test_filter_keeps_long_hairline_inside_canvas(self) -> None:
        kept, removed = filter_decorative_components(
            [_component(10, 50, 60, 1, 60)],
            image_width=100,
            image_height=100,
        )

        self.assertEqual(len(kept), 1)
        self.assertEqual(len(removed), 0)

    def test_filter_drops_tiny_compact_block_inside_canvas(self) -> None:
        kept, removed = filter_decorative_components(
            [_component(40, 40, 4, 4, 12)],
            image_width=100,
            image_height=100,
        )

        self.assertEqual(len(kept), 0)
        self.assertEqual(len(removed), 1)

    def test_filter_keeps_compact_block_with_meaningful_area(self) -> None:
        kept, removed = filter_decorative_components(
            [_component(35, 35, 12, 12, 96)],
            image_width=100,
            image_height=100,
        )

        self.assertEqual(len(kept), 1)
        self.assertEqual(len(removed), 0)

    def test_filter_drops_enclosed_hairline_residual_inside_large_component(self) -> None:
        components = [
            _component(10, 10, 80, 80, 1600),
            _component(30, 14, 20, 1, 20),
        ]

        kept, removed = filter_decorative_components(
            components,
            image_width=100,
            image_height=100,
        )

        self.assertEqual(len(kept), 1)
        self.assertEqual(len(removed), 1)

    def test_filter_drops_enclosed_tiny_compact_residual_inside_large_component(self) -> None:
        components = [
            _component(10, 10, 80, 80, 1600),
            _component(45, 45, 6, 6, 8),
        ]

        kept, removed = filter_decorative_components(
            components,
            image_width=100,
            image_height=100,
        )

        self.assertEqual(len(kept), 1)
        self.assertEqual(len(removed), 1)

    def test_filter_keeps_enclosed_meaningful_component_inside_large_component(self) -> None:
        components = [
            _component(10, 10, 80, 80, 1600),
            _component(35, 35, 20, 20, 180),
        ]

        kept, removed = filter_decorative_components(
            components,
            image_width=100,
            image_height=100,
        )

        self.assertEqual(len(kept), 2)
        self.assertEqual(len(removed), 0)

    def test_filter_drops_enclosed_edge_attached_slender_strip_inside_tighter_container(self) -> None:
        components = [
            _component(0, 0, 200, 200, 9000),
            _component(40, 40, 50, 60, 1600),
            _component(42, 44, 4, 40, 120),
        ]

        kept, removed = filter_decorative_components(
            components,
            image_width=200,
            image_height=200,
        )

        self.assertEqual(len(kept), 2)
        self.assertEqual(len(removed), 1)

    def test_filter_keeps_enclosed_meaningful_long_inner_line(self) -> None:
        components = [
            _component(0, 0, 200, 200, 9000),
            _component(40, 40, 50, 60, 1600),
            _component(60, 46, 4, 52, 208),
        ]

        kept, removed = filter_decorative_components(
            components,
            image_width=200,
            image_height=200,
        )

        self.assertEqual(len(kept), 3)
        self.assertEqual(len(removed), 0)

    def test_filter_drops_enclosed_tiny_corner_fragment_inside_tighter_container(self) -> None:
        components = [
            _component(0, 0, 200, 200, 9000),
            _component(40, 40, 60, 60, 1800),
            _component(44, 44, 6, 6, 18),
        ]

        kept, removed = filter_decorative_components(
            components,
            image_width=200,
            image_height=200,
        )

        self.assertEqual(len(kept), 2)
        self.assertEqual(len(removed), 1)


if __name__ == "__main__":
    unittest.main()
