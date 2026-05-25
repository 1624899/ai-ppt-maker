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

    def test_split_transparent_png_classic_mode_merges_compact_fragment_cluster(self) -> None:
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

            self.assertEqual(manifest["count"], 1)
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

    def test_split_transparent_png_filters_components_by_min_width_and_height(self) -> None:
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

            self.assertEqual(manifest["count"], 1)
            self.assertEqual(manifest["min_width"], 6)
            self.assertEqual(manifest["min_height"], 6)

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
