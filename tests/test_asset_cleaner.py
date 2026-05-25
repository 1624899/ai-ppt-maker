from __future__ import annotations

import unittest

import numpy as np

from ppt_system.asset_cleaner import restore_removed_regions


class AssetCleanerTests(unittest.TestCase):
    def test_restore_removed_regions_repaints_removed_icon_area(self) -> None:
        image = np.zeros((40, 60, 4), dtype=np.uint8)
        image[5:35, 5:55] = [248, 248, 248, 255]
        image[12:28, 20:40] = [20, 80, 220, 255]

        fill_mask = np.zeros((40, 60), dtype=bool)
        fill_mask[12:28, 20:40] = True

        cleaned = restore_removed_regions(image, fill_mask=fill_mask)

        center_rgb = cleaned[20, 30, :3]
        self.assertGreaterEqual(int(cleaned[20, 30, 3]), 240)
        self.assertGreaterEqual(int(center_rgb[0]), 230)
        self.assertGreaterEqual(int(center_rgb[1]), 230)
        self.assertGreaterEqual(int(center_rgb[2]), 230)


if __name__ == "__main__":
    unittest.main()
