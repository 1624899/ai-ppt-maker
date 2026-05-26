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
                filter_decorative_fragments=False,
            )

            self.assertEqual(manifest["count"], 2)
            saved = json.loads((out_dir / "assets.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["merge_distance"], 0)
            self.assertEqual(saved["split_mode"], "classic")

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
                filter_decorative_fragments=False,
            )

            self.assertEqual(manifest["count"], 2)
            self.assertEqual(manifest["split_mode"], "classic")

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
                filter_decorative_fragments=False,
            )

            self.assertEqual(manifest["count"], 3)
            self.assertEqual(manifest["split_mode"], "classic")

    def test_split_transparent_png_filters_tiny_edge_fragments_by_default(self) -> None:
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

            self.assertEqual(manifest["count"], 2)
            self.assertEqual(manifest["filtered_out_count"], 1)

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
            self.assertEqual(manifest["filtered_out_count"], 0)

    def test_split_transparent_png_semantic_mode_records_mode(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "sample.png"
            out_dir = root / "assets"
            image = np.zeros((80, 120, 4), dtype=np.uint8)
            image[10:70, 10:110] = [250, 250, 250, 255]
            image[10:70, 10:13] = [0, 80, 220, 255]
            image[10:70, 107:110] = [0, 80, 220, 255]
            image[10:13, 10:110] = [0, 80, 220, 255]
            image[67:70, 10:110] = [0, 80, 220, 255]
            image[28:48, 44:64] = [0, 80, 220, 255]
            Image.fromarray(image, mode="RGBA").save(image_path)

            manifest = split_transparent_png(
                image_path,
                out_dir,
                min_area=1,
                merge_distance=6,
                filter_decorative_fragments=False,
                split_mode="semantic",
            )

            self.assertEqual(manifest["split_mode"], "semantic")
            self.assertGreaterEqual(manifest["count"], 2)

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
                filter_decorative_fragments=False,
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
                filter_decorative_fragments=False,
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
                filter_decorative_fragments=False,
            )

            self.assertEqual(manifest["count"], 2)
            self.assertTrue(any(asset["width"] == 5 and asset["height"] == 42 for asset in manifest["assets"]))

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
                filter_decorative_fragments=False,
            )

            stale_asset = out_dir / "asset_999.png"
            stale_asset.write_bytes(b"stale")

            split_transparent_png(
                image_path,
                out_dir,
                min_area=1,
                merge_distance=0,
                filter_decorative_fragments=False,
            )

            self.assertFalse(stale_asset.exists())
            saved = json.loads((out_dir / "assets.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["count"], 2)
            self.assertEqual(len(list(out_dir.glob("asset_*.png"))), 2)


if __name__ == "__main__":
    unittest.main()
