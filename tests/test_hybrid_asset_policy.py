from __future__ import annotations

import unittest

from ppt_system.export.hybrid_asset_policy import should_keep_hybrid_asset


class HybridAssetPolicyTests(unittest.TestCase):
    def test_large_structural_asset_is_filtered(self):
        asset = {"left": 100, "top": 100, "width": 900, "height": 300, "area": 180000}
        self.assertFalse(should_keep_hybrid_asset(asset, {"native_blueprint": []}, 2000, 1125))

    def test_asset_inside_visual_region_is_kept(self):
        page = {"native_blueprint": [{"kind": "visual", "left": 900, "top": 100, "width": 900, "height": 800}]}
        asset = {"left": 1000, "top": 200, "width": 600, "height": 500, "area": 250000}
        self.assertTrue(should_keep_hybrid_asset(asset, page, 2000, 1125))

    def test_small_dense_icon_is_kept(self):
        asset = {"left": 100, "top": 100, "width": 90, "height": 90, "area": 5000}
        self.assertTrue(should_keep_hybrid_asset(asset, {"native_blueprint": []}, 2000, 1125))


if __name__ == "__main__":
    unittest.main()
