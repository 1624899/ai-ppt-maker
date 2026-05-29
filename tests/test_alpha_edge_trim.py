from __future__ import annotations

import unittest

import numpy as np

from ppt_system.alpha_edge_trim import remove_outer_background_like_fringe, tighten_outer_alpha_fringe


class AlphaEdgeTrimTests(unittest.TestCase):
    def test_tighten_outer_alpha_fringe_reduces_supported_soft_ring(self) -> None:
        alpha = np.array(
            [
                [0, 0, 0, 0, 0],
                [0, 96, 128, 96, 0],
                [0, 128, 255, 128, 0],
                [0, 96, 128, 96, 0],
                [0, 0, 0, 0, 0],
            ],
            dtype=np.uint8,
        )

        result = tighten_outer_alpha_fringe(alpha)

        self.assertEqual(int(result[2, 2]), 255)
        self.assertLess(int(result[1, 2]), int(alpha[1, 2]))
        self.assertLess(int(result[2, 1]), int(alpha[2, 1]))
        self.assertLess(int(result[1, 1]), int(alpha[1, 1]))

    def test_tighten_outer_alpha_fringe_keeps_fully_opaque_thin_stroke(self) -> None:
        alpha = np.array(
            [
                [0, 255, 0],
                [0, 255, 0],
                [0, 255, 0],
            ],
            dtype=np.uint8,
        )

        result = tighten_outer_alpha_fringe(alpha)

        np.testing.assert_array_equal(result, alpha)

    def test_tighten_outer_alpha_fringe_removes_detached_weak_soft_pixel(self) -> None:
        alpha = np.array(
            [
                [0, 0, 0, 0, 0],
                [0, 255, 255, 0, 0],
                [0, 255, 255, 0, 0],
                [0, 0, 0, 48, 0],
                [0, 0, 0, 0, 0],
            ],
            dtype=np.uint8,
        )

        result = tighten_outer_alpha_fringe(alpha)

        self.assertEqual(int(result[3, 3]), 0)

    def test_remove_outer_background_like_fringe_can_cut_multiple_exposed_rings(self) -> None:
        alpha = np.zeros((5, 5), dtype=np.uint8)
        alpha[1:4, 1:4] = 255
        background_like_mask = np.zeros((5, 5), dtype=bool)
        background_like_mask[1, 1:4] = True
        background_like_mask[2, 2] = True

        result = remove_outer_background_like_fringe(
            alpha,
            background_like_mask=background_like_mask,
            protected_mask=None,
        )

        self.assertEqual(int(result[1, 1]), 0)
        self.assertEqual(int(result[1, 2]), 0)
        self.assertEqual(int(result[1, 3]), 0)
        self.assertEqual(int(result[2, 2]), 0)
        self.assertEqual(int(result[3, 2]), 255)

    def test_remove_outer_background_like_fringe_keeps_protected_fill_block(self) -> None:
        alpha = np.zeros((5, 5), dtype=np.uint8)
        alpha[1:4, 1:4] = 180
        background_like_mask = alpha > 0
        protected_mask = np.zeros((5, 5), dtype=bool)
        protected_mask[1:4, 1:4] = True

        result = remove_outer_background_like_fringe(
            alpha,
            background_like_mask=background_like_mask,
            protected_mask=protected_mask,
        )

        np.testing.assert_array_equal(result, alpha)


if __name__ == "__main__":
    unittest.main()
