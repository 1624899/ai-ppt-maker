from __future__ import annotations

import unittest

import numpy as np

from ppt_system.alpha_matte_refinement import BackgroundModel, refine_alpha_matte


class AlphaMatteRefinementTests(unittest.TestCase):
    def test_refine_alpha_matte_bridges_single_pixel_gap_in_thin_line(self) -> None:
        source = np.full((3, 5, 4), 255, dtype=np.uint8)
        source[1, 0:5, :3] = np.array([30, 80, 220], dtype=np.uint8)

        removed = np.array(source, copy=True)
        removed[:, :, 3] = 0
        removed[1, 1, 3] = 255
        removed[1, 3, 3] = 255

        refined = refine_alpha_matte(
            source,
            removed,
            background=BackgroundModel(color=np.array([255, 255, 255], dtype=np.int16), tolerance=12),
        )

        self.assertGreater(refined[1, 2, 3], 0)
        self.assertGreaterEqual(refined[1, 2, 3], min(refined[1, 1, 3], refined[1, 3, 3]) // 2)

    def test_refine_alpha_matte_preserves_connected_soft_edge_and_removes_isolated_weak_noise(self) -> None:
        source = np.full((7, 7, 4), 255, dtype=np.uint8)
        source[2:5, 2:5, :3] = np.array([30, 80, 220], dtype=np.uint8)
        source[3, 1, :3] = np.array([242, 242, 248], dtype=np.uint8)
        source[0, 6, :3] = np.array([247, 247, 250], dtype=np.uint8)

        removed = np.array(source, copy=True)
        removed[:, :, 3] = 0
        removed[2:5, 2:5, 3] = 255
        removed[3, 1, 3] = 18
        removed[0, 6, 3] = 18

        refined = refine_alpha_matte(
            source,
            removed,
            background=BackgroundModel(color=np.array([255, 255, 255], dtype=np.int16), tolerance=12),
        )

        self.assertGreater(refined[3, 1, 3], 0)
        self.assertEqual(refined[0, 6, 3], 0)
        self.assertEqual(refined[3, 3, 3], 255)

    def test_refine_alpha_matte_decontaminates_white_edge_color(self) -> None:
        source = np.full((1, 3, 4), 255, dtype=np.uint8)
        source[0, 1, :3] = np.array([255, 128, 128], dtype=np.uint8)
        source[0, 2, :3] = np.array([220, 30, 30], dtype=np.uint8)

        removed = np.array(source, copy=True)
        removed[:, :, 3] = np.array([[0, 128, 255]], dtype=np.uint8)

        refined = refine_alpha_matte(
            source,
            removed,
            background=BackgroundModel(color=np.array([255, 255, 255], dtype=np.int16), tolerance=12),
        )

        self.assertLess(refined[0, 1, 1], 40)
        self.assertLess(refined[0, 1, 2], 40)
        self.assertEqual(refined[0, 2, 3], 255)

    def test_refine_alpha_matte_suppresses_sparse_white_fringe_attached_to_subject(self) -> None:
        source = np.full((5, 5, 4), 255, dtype=np.uint8)
        source[2, 1:4, :3] = np.array([30, 80, 220], dtype=np.uint8)
        source[1, 4, :3] = np.array([244, 244, 248], dtype=np.uint8)

        removed = np.array(source, copy=True)
        removed[:, :, 3] = 0
        removed[2, 1:4, 3] = 255
        removed[1, 4, 3] = 36

        refined = refine_alpha_matte(
            source,
            removed,
            background=BackgroundModel(color=np.array([255, 255, 255], dtype=np.int16), tolerance=12),
        )

        self.assertEqual(refined[1, 4, 3], 0)
        self.assertEqual(refined[2, 2, 3], 255)


if __name__ == "__main__":
    unittest.main()
