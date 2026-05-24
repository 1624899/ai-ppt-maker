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


if __name__ == "__main__":
    unittest.main()
