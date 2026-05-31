from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw

from ppt_system.image.asset_alignment_runtime import analyze_text_asset_overlaps


class AssetAlignmentRuntimeTests(unittest.TestCase):
    def test_analyze_text_asset_overlaps_reports_overlap_boxes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            assets_dir = root / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            source_path = root / "source.png"
            Image.new("RGBA", (400, 240), (255, 255, 255, 0)).save(source_path)

            asset = Image.new("RGBA", (120, 80), (255, 255, 255, 0))
            draw = ImageDraw.Draw(asset)
            draw.rounded_rectangle((0, 0, 119, 79), radius=8, outline=(0, 80, 220, 255), width=3)
            asset.save(assets_dir / "asset_001.png")

            manifest_path = assets_dir / "assets.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "source_image": str(source_path),
                        "image_width": 400,
                        "image_height": 240,
                        "assets": [
                            {"index": 1, "file": "asset_001.png", "left": 80, "top": 80, "width": 120, "height": 80}
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            report = analyze_text_asset_overlaps(
                manifest_path=manifest_path,
                page_script='add_text(slide, "标题", 76, 76, 128, 88, size=20)',
                current_adjustments={},
            )

            self.assertEqual(report.total_boxes, 1)
            self.assertEqual(report.overlap_box_count, 1)
            self.assertGreater(report.max_overlap_pixels, 0)
            self.assertEqual(report.overlapping_box_indices, [1])


if __name__ == "__main__":
    unittest.main()
