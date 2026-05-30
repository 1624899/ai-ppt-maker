from __future__ import annotations

import unittest

import numpy as np

from ppt_system.image.component_color_grouping import merge_color_coherent_fragments


def _component(left: int, top: int, width: int, height: int, color: tuple[int, int, int]) -> tuple[dict[str, object], np.ndarray]:
    component = {
        "left": left,
        "top": top,
        "right": left + width,
        "bottom": top + height,
        "area": width * height,
        "mask": np.ones((height, width), dtype=bool),
    }
    patch = np.zeros((height, width, 4), dtype=np.uint8)
    patch[:, :, 0] = color[0]
    patch[:, :, 1] = color[1]
    patch[:, :, 2] = color[2]
    patch[:, :, 3] = 255
    return component, patch


class ComponentColorGroupingTests(unittest.TestCase):
    def test_merge_color_coherent_fragments_merges_nearby_same_color_line_group(self) -> None:
        image = np.zeros((120, 120, 4), dtype=np.uint8)
        specs = [
            (20, 20, 18, 4),
            (46, 20, 18, 4),
            (20, 32, 4, 18),
            (60, 32, 4, 18),
            (20, 56, 18, 4),
            (46, 56, 18, 4),
        ]
        components: list[dict[str, object]] = []
        for left, top, width, height in specs:
            component, patch = _component(left, top, width, height, (25, 90, 255))
            image[top : top + height, left : left + width] = patch
            components.append(component)

        merged = merge_color_coherent_fragments(
            components,
            image_array=image,
            image_width=120,
            image_height=120,
            merge_distance=6,
        )

        self.assertEqual(len(merged), 1)
        self.assertTrue(bool(merged[0].get("is_color_coherent_group", False)))
        self.assertEqual(int(merged[0].get("color_group_size", 0)), 6)

    def test_merge_color_coherent_fragments_keeps_different_color_fragments_separate(self) -> None:
        image = np.zeros((120, 120, 4), dtype=np.uint8)
        blue_component, blue_patch = _component(20, 20, 18, 4, (25, 90, 255))
        cyan_component, cyan_patch = _component(46, 20, 18, 4, (25, 180, 255))
        image[20:24, 20:38] = blue_patch
        image[20:24, 46:64] = cyan_patch

        merged = merge_color_coherent_fragments(
            [blue_component, cyan_component],
            image_array=image,
            image_width=120,
            image_height=120,
            merge_distance=6,
        )

        self.assertEqual(len(merged), 2)

    def test_merge_color_coherent_fragments_merges_line_segments_with_whitened_corner_connector(self) -> None:
        image = np.zeros((120, 120, 4), dtype=np.uint8)
        components: list[dict[str, object]] = []
        specs = [
            (20, 30, 14, 4, (0, 0, 250)),
            (42, 30, 14, 4, (0, 0, 250)),
            (58, 30, 12, 8, (210, 228, 255)),
            (66, 38, 4, 14, (0, 0, 250)),
            (66, 60, 4, 14, (0, 0, 250)),
        ]
        for left, top, width, height, color in specs:
            component, patch = _component(left, top, width, height, color)
            if color[0] > 150:
                # 用一半鲜艳蓝色、一半发白蓝色模拟抠图污染后的拐角连接块。
                patch[:, :, 0] = 0
                patch[:, :, 1] = 0
                patch[:, :, 2] = 250
                patch[: height // 2, :, 0] = 210
                patch[: height // 2, :, 1] = 228
                patch[: height // 2, :, 2] = 255
            image[top : top + height, left : left + width] = patch
            components.append(component)

        merged = merge_color_coherent_fragments(
            components,
            image_array=image,
            image_width=120,
            image_height=120,
            merge_distance=6,
        )

        self.assertEqual(len(merged), 1)
        self.assertTrue(bool(merged[0].get("is_color_coherent_group", False)))
        self.assertEqual(int(merged[0].get("color_group_size", 0)), 5)
