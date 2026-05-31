from __future__ import annotations

import unittest

import numpy as np

from ppt_system.image.alpha_matte_refinement import (
    BackgroundModel,
    build_color_guided_alpha,
    refine_alpha_matte,
)
from ppt_system.image.visual_white_axis import build_visual_white_mask
from ppt_system.image.white_axis_cutout import build_white_axis_cutout


class AlphaMatteRefinementTests(unittest.TestCase):
    def test_visual_white_mask_detects_neutral_highlight_not_pale_color(self) -> None:
        rgb = np.array(
            [
                [[254, 254, 254], [248, 248, 249], [245, 248, 254], [231, 240, 254]],
            ],
            dtype=np.uint8,
        )

        mask = build_visual_white_mask(
            rgb,
            background_color=np.array([253, 253, 253], dtype=np.int16),
            background_tolerance=12,
        )

        self.assertTrue(bool(mask[0, 0]))
        self.assertTrue(bool(mask[0, 1]))
        self.assertTrue(bool(mask[0, 2]))
        self.assertFalse(bool(mask[0, 3]))

    def test_refine_alpha_matte_removes_white_inside_colored_shape(self) -> None:
        source = np.full((7, 7, 4), 255, dtype=np.uint8)
        source[1:6, 1:6, :3] = np.array([30, 80, 220], dtype=np.uint8)
        source[3, 3, :3] = np.array([254, 254, 254], dtype=np.uint8)
        removed = source.copy()

        result = refine_alpha_matte(
            source,
            removed,
            background=BackgroundModel(
                color=np.array([253, 253, 253], dtype=np.int16),
                tolerance=12,
                color_cast_tolerance=8,
            ),
        )

        self.assertEqual(int(result[3, 3, 3]), 0)
        self.assertGreaterEqual(int(result[2, 3, 3]), 232)
        self.assertEqual(int(result[0, 0, 3]), 0)

    def test_white_axis_cutout_never_keeps_alpha_on_visual_white_pixels(self) -> None:
        source = np.full((5, 8, 4), 255, dtype=np.uint8)
        source[2, 1:4, :3] = np.array([30, 80, 220], dtype=np.uint8)
        source[2, 4, :3] = np.array([248, 248, 249], dtype=np.uint8)
        source[2, 5, :3] = np.array([30, 80, 220], dtype=np.uint8)

        artifacts = build_white_axis_cutout(
            source,
            background_color=np.array([253, 253, 253], dtype=np.int16),
            background_tolerance=12,
            background_cast_tolerance=8,
        )

        self.assertEqual(int(artifacts.final_alpha[2, 4]), 0)
        self.assertFalse(bool(artifacts.connected_mask[2, 4]))
        self.assertGreaterEqual(int(artifacts.final_alpha[2, 2]), 232)
        self.assertGreaterEqual(int(artifacts.final_alpha[2, 5]), 232)

    def test_build_color_guided_alpha_is_compatibility_alias_for_final_alpha(self) -> None:
        source = np.full((3, 3, 4), 255, dtype=np.uint8)
        source[1, 1, :3] = np.array([20, 40, 90], dtype=np.uint8)
        background = BackgroundModel(
            color=np.array([255, 255, 255], dtype=np.int16),
            tolerance=12,
            color_cast_tolerance=8,
        )

        alpha = build_color_guided_alpha(source, background=background)

        self.assertEqual(int(alpha[0, 0]), 0)
        self.assertGreaterEqual(int(alpha[1, 1]), 232)


if __name__ == "__main__":
    unittest.main()
