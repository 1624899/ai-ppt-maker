from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image

from ppt_system.splitter import split_transparent_png


class SplitterTests(unittest.TestCase):
    def test_split_transparent_png_keeps_components_separate_without_merge(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "sample.png"
            out_dir = root / "assets"
            image = np.zeros((20, 20, 4), dtype=np.uint8)
            image[2:5, 2:5] = [255, 0, 0, 255]
            image[2:5, 10:13] = [0, 128, 255, 255]
            Image.fromarray(image, mode="RGBA").save(image_path)

            manifest = split_transparent_png(
                image_path,
                out_dir,
                min_area=1,
                merge_distance=0,
            )

            self.assertEqual(manifest["count"], 2)
            saved = json.loads((out_dir / "assets.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["merge_distance"], 0)

    def test_split_transparent_png_classic_mode_keeps_nearby_components_separate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "sample.png"
            out_dir = root / "assets"
            image = np.zeros((20, 20, 4), dtype=np.uint8)
            image[2:5, 2:5] = [255, 0, 0, 255]
            image[2:5, 8:11] = [0, 128, 255, 255]
            Image.fromarray(image, mode="RGBA").save(image_path)

            manifest = split_transparent_png(
                image_path,
                out_dir,
                min_area=1,
                merge_distance=2,
            )

            self.assertEqual(manifest["count"], 2)

    def test_split_transparent_png_classic_mode_keeps_compact_fragment_cluster_separate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "sample.png"
            out_dir = root / "assets"
            image = np.zeros((40, 40, 4), dtype=np.uint8)
            image[5:11, 5:11] = [255, 0, 0, 255]
            image[5:11, 14:20] = [255, 0, 0, 255]
            image[13:19, 9:15] = [255, 0, 0, 255]
            Image.fromarray(image, mode="RGBA").save(image_path)

            manifest = split_transparent_png(
                image_path,
                out_dir,
                min_area=1,
                merge_distance=6,
            )

            self.assertEqual(manifest["count"], 3)

    def test_split_transparent_png_keeps_tiny_edge_fragments_after_filter_removal(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "sample.png"
            out_dir = root / "assets"
            image = np.zeros((100, 100, 4), dtype=np.uint8)
            image[20:50, 20:50] = [255, 0, 0, 255]
            image[60:66, 60:66] = [0, 128, 255, 255]
            image[10:35, 99:100] = [0, 0, 0, 255]
            Image.fromarray(image, mode="RGBA").save(image_path)

            manifest = split_transparent_png(image_path, out_dir, min_area=1, merge_distance=0)

            self.assertEqual(manifest["count"], 3)

    def test_split_transparent_png_keeps_large_edge_component(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "sample.png"
            out_dir = root / "assets"
            image = np.zeros((100, 100, 4), dtype=np.uint8)
            image[25:55, 25:55] = [255, 0, 0, 255]
            image[10:30, 90:100] = [0, 128, 255, 255]
            Image.fromarray(image, mode="RGBA").save(image_path)

            manifest = split_transparent_png(image_path, out_dir, min_area=1, merge_distance=0)

            self.assertEqual(manifest["count"], 2)

    def test_split_transparent_png_filters_only_components_small_in_both_dimensions(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "sample.png"
            out_dir = root / "assets"
            image = np.zeros((60, 60, 4), dtype=np.uint8)
            image[5:25, 5:25] = [255, 0, 0, 255]
            image[30:50, 40:43] = [0, 128, 255, 255]
            image[45:48, 10:30] = [0, 255, 0, 255]
            Image.fromarray(image, mode="RGBA").save(image_path)

            manifest = split_transparent_png(
                image_path,
                out_dir,
                min_area=1,
                min_width=6,
                min_height=6,
                merge_distance=0,
            )

            self.assertEqual(manifest["count"], 3)
            self.assertEqual(manifest["min_width"], 6)
            self.assertEqual(manifest["min_height"], 6)

    def test_split_transparent_png_keeps_horizontal_dashed_cluster_when_height_below_threshold(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "sample.png"
            out_dir = root / "assets"
            image = np.zeros((80, 80, 4), dtype=np.uint8)
            image[10:30, 10:30] = [255, 0, 0, 255]
            image[50:55, 20:30] = [0, 128, 255, 255]
            image[50:55, 36:46] = [0, 128, 255, 255]
            image[50:55, 52:62] = [0, 128, 255, 255]
            image[60:65, 62:67] = [0, 255, 0, 255]
            Image.fromarray(image, mode="RGBA").save(image_path)

            manifest = split_transparent_png(
                image_path,
                out_dir,
                min_area=8,
                min_width=7,
                min_height=6,
                merge_distance=6,
            )

            self.assertEqual(manifest["count"], 2)
            self.assertTrue(any(asset["width"] == 42 and asset["height"] == 5 for asset in manifest["assets"]))

    def test_split_transparent_png_keeps_vertical_dashed_cluster_when_width_below_threshold(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "sample.png"
            out_dir = root / "assets"
            image = np.zeros((80, 80, 4), dtype=np.uint8)
            image[10:30, 10:30] = [255, 0, 0, 255]
            image[20:30, 50:55] = [0, 128, 255, 255]
            image[36:46, 50:55] = [0, 128, 255, 255]
            image[52:62, 50:55] = [0, 128, 255, 255]
            image[62:67, 60:65] = [0, 255, 0, 255]
            Image.fromarray(image, mode="RGBA").save(image_path)

            manifest = split_transparent_png(
                image_path,
                out_dir,
                min_area=8,
                min_width=7,
                min_height=6,
                merge_distance=6,
            )

            self.assertEqual(manifest["count"], 2)
            self.assertTrue(any(asset["width"] == 5 and asset["height"] == 42 for asset in manifest["assets"]))

    def test_split_transparent_png_keeps_near_edge_dashed_cluster(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "sample.png"
            out_dir = root / "assets"
            image = np.zeros((100, 100, 4), dtype=np.uint8)
            image[20:45, 15:35] = [255, 0, 0, 255]
            image[8:13, 58:68] = [0, 128, 255, 255]
            image[8:13, 72:82] = [0, 128, 255, 255]
            image[8:13, 86:96] = [0, 128, 255, 255]
            Image.fromarray(image, mode="RGBA").save(image_path)

            manifest = split_transparent_png(
                image_path,
                out_dir,
                min_area=8,
                merge_distance=6,
            )

            self.assertEqual(manifest["count"], 2)
            self.assertTrue(any(asset["width"] == 38 and asset["height"] == 5 for asset in manifest["assets"]))

    def test_split_transparent_png_merges_same_color_mixed_orientation_dash_loop(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "sample.png"
            out_dir = root / "assets"
            image = np.zeros((120, 120, 4), dtype=np.uint8)
            image[15:35, 10:30] = [255, 0, 0, 255]
            image[30:34, 40:58] = [20, 90, 255, 255]
            image[30:34, 66:84] = [20, 90, 255, 255]
            image[42:60, 40:44] = [20, 90, 255, 255]
            image[42:60, 80:84] = [20, 90, 255, 255]
            image[66:70, 40:58] = [20, 90, 255, 255]
            image[66:70, 66:84] = [20, 90, 255, 255]
            Image.fromarray(image, mode="RGBA").save(image_path)

            manifest = split_transparent_png(
                image_path,
                out_dir,
                min_area=8,
                merge_distance=6,
            )

            self.assertEqual(manifest["count"], 2)
            self.assertTrue(any(asset["width"] == 44 and asset["height"] == 40 for asset in manifest["assets"]))

    def test_split_transparent_png_keeps_low_saturation_light_residual_and_colored_dash(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "sample.png"
            out_dir = root / "assets"
            image = np.zeros((120, 120, 4), dtype=np.uint8)
            image[20:45, 20:45] = [255, 0, 0, 255]
            image[60:64, 40:58] = [255, 120, 20, 255]
            image[74:78, 40:58] = [255, 120, 20, 255]
            image[86:93, 88:95] = [210, 218, 242, 255]
            image[88:91, 90:93] = [255, 255, 255, 255]
            Image.fromarray(image, mode="RGBA").save(image_path)

            manifest = split_transparent_png(
                image_path,
                out_dir,
                min_area=8,
                merge_distance=6,
            )

            self.assertEqual(manifest["count"], 4)
            self.assertEqual(sum(1 for asset in manifest["assets"] if asset["width"] == 18 and asset["height"] == 4), 2)
            self.assertTrue(any(asset["left"] == 88 and asset["top"] == 86 and asset["width"] == 7 for asset in manifest["assets"]))

    def test_split_transparent_png_core_threshold_still_excludes_isolated_weak_alpha_component(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "sample.png"
            out_dir = root / "assets"
            image = np.zeros((40, 40, 4), dtype=np.uint8)
            image[10:20, 10:20] = [255, 0, 0, 255]
            image[30, 30] = [255, 255, 255, 24]
            image[30, 31] = [245, 245, 245, 24]
            Image.fromarray(image, mode="RGBA").save(image_path)

            manifest = split_transparent_png(
                image_path,
                out_dir,
                min_area=1,
                merge_distance=0,
            )

            self.assertEqual(manifest["count"], 1)
            self.assertEqual(manifest["raw_component_count"], 1)

    def test_split_transparent_png_uses_core_mask_to_ignore_weak_alpha_bridge(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "sample.png"
            out_dir = root / "assets"
            image = np.zeros((32, 32, 4), dtype=np.uint8)
            image[10:18, 4:12] = [255, 0, 0, 255]
            image[10:18, 20:28] = [0, 128, 255, 255]
            image[13:15, 12:20] = [255, 255, 255, 20]
            Image.fromarray(image, mode="RGBA").save(image_path)

            manifest = split_transparent_png(
                image_path,
                out_dir,
                min_area=1,
                merge_distance=0,
            )

            self.assertEqual(manifest["count"], 2)
            self.assertEqual(manifest["raw_component_count"], 2)
            self.assertEqual(manifest["alpha_core_threshold"], 48)

    def test_split_transparent_png_keeps_visual_soft_edge_after_core_split(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "sample.png"
            out_dir = root / "assets"
            image = np.zeros((32, 32, 4), dtype=np.uint8)
            image[10:18, 10:18] = [255, 0, 0, 255]
            image[9:19, 9] = [255, 0, 0, 20]
            image[9:19, 18] = [255, 0, 0, 20]
            image[9, 9:19] = [255, 0, 0, 20]
            image[18, 9:19] = [255, 0, 0, 20]
            Image.fromarray(image, mode="RGBA").save(image_path)

            manifest = split_transparent_png(
                image_path,
                out_dir,
                min_area=1,
                merge_distance=0,
            )

            self.assertEqual(manifest["count"], 1)
            asset = manifest["assets"][0]
            self.assertEqual((asset["left"], asset["top"], asset["width"], asset["height"]), (9, 9, 10, 10))
            saved = np.array(Image.open(out_dir / asset["file"]).convert("RGBA"))
            self.assertGreater(int(saved[0, 0, 3]), 0)

    def test_split_transparent_png_four_connected_core_keeps_diagonal_touch_separate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "sample.png"
            out_dir = root / "assets"
            image = np.zeros((24, 24, 4), dtype=np.uint8)
            image[5:10, 5:10] = [255, 0, 0, 255]
            image[10:15, 10:15] = [0, 128, 255, 255]
            Image.fromarray(image, mode="RGBA").save(image_path)

            manifest = split_transparent_png(
                image_path,
                out_dir,
                min_area=1,
                merge_distance=0,
            )

            self.assertEqual(manifest["count"], 2)

    def test_split_transparent_png_structural_merge_keeps_collinear_dashes_together(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "sample.png"
            out_dir = root / "assets"
            image = np.zeros((60, 80, 4), dtype=np.uint8)
            image[20:24, 10:22] = [20, 90, 255, 255]
            image[20:24, 30:42] = [20, 90, 255, 255]
            image[20:24, 50:62] = [20, 90, 255, 255]
            Image.fromarray(image, mode="RGBA").save(image_path)

            manifest = split_transparent_png(
                image_path,
                out_dir,
                min_area=1,
                merge_distance=6,
            )

            self.assertEqual(manifest["count"], 1)
            self.assertEqual((manifest["assets"][0]["width"], manifest["assets"][0]["height"]), (52, 4))

    def test_split_transparent_png_groups_icon_fragments_inside_same_frame_region(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "sample.png"
            out_dir = root / "assets"
            image = np.zeros((80, 100, 4), dtype=np.uint8)

            image[10:14, 10:70] = [40, 70, 120, 255]
            image[46:50, 10:70] = [40, 70, 120, 255]
            image[10:50, 10:14] = [40, 70, 120, 255]
            image[10:50, 66:70] = [40, 70, 120, 255]

            image[20:24, 22:42] = [0, 140, 255, 255]
            image[20:36, 38:42] = [0, 140, 255, 255]
            image[32:36, 38:56] = [0, 140, 255, 255]
            Image.fromarray(image, mode="RGBA").save(image_path)

            manifest = split_transparent_png(
                image_path,
                out_dir,
                min_area=1,
                merge_distance=6,
            )

            self.assertEqual(manifest["count"], 2)
            self.assertTrue(any(asset["width"] >= 58 and asset["height"] >= 38 for asset in manifest["assets"]))
            self.assertTrue(any(32 <= asset["width"] <= 36 and 16 <= asset["height"] <= 20 for asset in manifest["assets"]))

    def test_split_transparent_png_separates_icon_from_frame_when_thin_bridge_connects_them(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "sample.png"
            out_dir = root / "assets"
            image = np.zeros((90, 110, 4), dtype=np.uint8)

            image[12:16, 14:82] = [50, 90, 130, 255]
            image[54:58, 14:82] = [50, 90, 130, 255]
            image[12:58, 14:18] = [50, 90, 130, 255]
            image[12:58, 78:82] = [50, 90, 130, 255]

            image[24:28, 30:48] = [255, 110, 30, 255]
            image[24:42, 44:48] = [255, 110, 30, 255]
            image[40:44, 44:62] = [255, 110, 30, 255]
            image[28:32, 47:49] = [255, 110, 30, 255]
            image[28:32, 49:79] = [255, 110, 30, 255]
            Image.fromarray(image, mode="RGBA").save(image_path)

            manifest = split_transparent_png(
                image_path,
                out_dir,
                min_area=1,
                merge_distance=6,
            )

            self.assertEqual(manifest["count"], 2)
            frame_assets = [asset for asset in manifest["assets"] if asset["width"] >= 64 and asset["height"] >= 44]
            icon_assets = [asset for asset in manifest["assets"] if 30 <= asset["width"] <= 42 and 18 <= asset["height"] <= 24]
            self.assertEqual(len(frame_assets), 1)
            self.assertEqual(len(icon_assets), 1)

    def test_split_transparent_png_cleans_stale_asset_files_before_rerun(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "sample.png"
            out_dir = root / "assets"
            image = np.zeros((40, 40, 4), dtype=np.uint8)
            image[5:15, 5:15] = [255, 0, 0, 255]
            image[20:30, 20:30] = [0, 128, 255, 255]
            Image.fromarray(image, mode="RGBA").save(image_path)

            split_transparent_png(
                image_path,
                out_dir,
                min_area=1,
                merge_distance=0,
            )

            stale_asset = out_dir / "asset_999.png"
            stale_asset.write_bytes(b"stale")

            split_transparent_png(
                image_path,
                out_dir,
                min_area=1,
                merge_distance=0,
            )

            self.assertFalse(stale_asset.exists())
            saved = json.loads((out_dir / "assets.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["count"], 2)
            self.assertEqual(len(list(out_dir.glob("asset_*.png"))), 2)

    def test_split_transparent_png_does_not_emit_svg_postprocess_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "sample.png"
            out_dir = root / "assets"
            image = np.zeros((64, 64, 4), dtype=np.uint8)
            image[8:56, 8] = [0, 128, 255, 255]
            image[8:56, 55] = [0, 128, 255, 255]
            image[8, 8:56] = [0, 128, 255, 255]
            image[55, 8:56] = [0, 128, 255, 255]
            Image.fromarray(image, mode="RGBA").save(image_path)

            manifest = split_transparent_png(
                image_path,
                out_dir,
                min_area=1,
                merge_distance=0,
            )

            self.assertEqual(manifest["count"], 1)
            self.assertFalse(any(out_dir.glob("asset_*.svg")))
            self.assertNotIn("warnings", manifest)
            self.assertNotIn("vector_file", manifest["assets"][0])


if __name__ == "__main__":
    unittest.main()
