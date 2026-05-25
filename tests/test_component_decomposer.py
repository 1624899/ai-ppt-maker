from __future__ import annotations

import unittest

import numpy as np

from ppt_system.component_decomposer import decompose_components


def _component(mask: np.ndarray) -> dict[str, object]:
    ys, xs = np.nonzero(mask)
    min_x = int(xs.min())
    max_x = int(xs.max())
    min_y = int(ys.min())
    max_y = int(ys.max())
    component_mask = mask[min_y : max_y + 1, min_x : max_x + 1].copy()
    return {
        "left": min_x,
        "top": min_y,
        "right": max_x + 1,
        "bottom": max_y + 1,
        "area": int(component_mask.sum()),
        "mask": component_mask,
    }


class ComponentDecomposerTests(unittest.TestCase):
    def test_decompose_components_splits_large_card_and_inner_icon(self) -> None:
        image = np.zeros((120, 160, 4), dtype=np.uint8)
        image[20:100, 20:140] = [250, 250, 250, 255]
        image[20:100, 20:23] = [30, 80, 220, 255]
        image[20:100, 137:140] = [30, 80, 220, 255]
        image[20:23, 20:140] = [30, 80, 220, 255]
        image[97:100, 20:140] = [30, 80, 220, 255]
        image[48:74, 56:84] = [30, 80, 220, 255]

        mask = image[..., 3] > 0
        components = [_component(mask)]

        decomposed = decompose_components(components, image_array=image)

        self.assertEqual(len(decomposed), 2)
        areas = sorted(int(item["area"]) for item in decomposed)
        self.assertEqual(areas[0], 728)
        self.assertGreater(areas[1], 8000)

    def test_decompose_components_keeps_edge_border_in_frame_asset(self) -> None:
        image = np.zeros((120, 160, 4), dtype=np.uint8)
        image[15:105, 15:145] = [250, 250, 250, 255]
        image[15:105, 15:18] = [30, 80, 220, 255]
        image[15:105, 142:145] = [30, 80, 220, 255]
        image[15:18, 15:145] = [30, 80, 220, 255]
        image[102:105, 15:145] = [30, 80, 220, 255]
        image[50:74, 36:60] = [30, 80, 220, 255]
        image[50:74, 100:124] = [30, 80, 220, 255]

        mask = image[..., 3] > 0
        components = [_component(mask)]

        decomposed = decompose_components(components, image_array=image)

        self.assertEqual(len(decomposed), 3)
        frame = max(decomposed, key=lambda item: int(item["area"]))
        self.assertEqual(int(frame["left"]), 15)
        self.assertEqual(int(frame["top"]), 15)
        self.assertEqual(int(frame["right"]), 145)
        self.assertEqual(int(frame["bottom"]), 105)


if __name__ == "__main__":
    unittest.main()
