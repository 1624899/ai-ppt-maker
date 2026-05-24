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

    def test_split_transparent_png_merges_nearby_components_without_filling_gap(self) -> None:
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

            self.assertEqual(manifest["count"], 1)
            asset = manifest["assets"][0]
            merged_image = Image.open(out_dir / str(asset["file"])).convert("RGBA")
            alpha = np.array(merged_image.getchannel("A"))
            self.assertEqual(int((alpha > 0).sum()), 18)
            self.assertTrue(np.all(alpha[:, 3:6] == 0))

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


if __name__ == "__main__":
    unittest.main()
