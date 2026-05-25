from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw

from ppt_system.asset_alignment_runtime import analyze_global_asset_alignment, analyze_text_asset_overlaps


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

    def test_analyze_global_asset_alignment_applies_stable_shift(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reference_path = root / "reference.png"
            assets_dir = root / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            source_path = root / "source.png"

            reference = Image.new("RGB", (400, 240), (255, 255, 255))
            draw = ImageDraw.Draw(reference)
            draw.rounded_rectangle((40, 70, 180, 185), radius=8, outline=(0, 80, 220), width=3)
            draw.rounded_rectangle((220, 70, 360, 185), radius=8, outline=(0, 80, 220), width=3)
            reference.save(reference_path)

            asset_1 = Image.new("RGBA", (140, 115), (255, 255, 255, 0))
            draw_1 = ImageDraw.Draw(asset_1)
            draw_1.rounded_rectangle((0, 0, 139, 114), radius=8, outline=(0, 80, 220, 255), width=3)
            asset_1.save(assets_dir / "asset_001.png")

            asset_2 = Image.new("RGBA", (140, 115), (255, 255, 255, 0))
            draw_2 = ImageDraw.Draw(asset_2)
            draw_2.rounded_rectangle((0, 0, 139, 114), radius=8, outline=(0, 80, 220, 255), width=3)
            asset_2.save(assets_dir / "asset_002.png")

            Image.new("RGBA", (400, 240), (255, 255, 255, 0)).save(source_path)
            manifest_path = assets_dir / "assets.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "source_image": str(source_path),
                        "image_width": 400,
                        "image_height": 240,
                        "assets": [
                            {"index": 1, "file": "asset_001.png", "left": 40, "top": 20, "width": 140, "height": 115},
                            {"index": 2, "file": "asset_002.png", "left": 220, "top": 20, "width": 140, "height": 115},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            decision = analyze_global_asset_alignment(
                reference_image=reference_path,
                manifest_path=manifest_path,
                page_script="",
                current_adjustments={},
                min_shift_px=12,
                max_center_gap=120,
            )

            self.assertIn(
                decision.reason,
                {"apply-global-shift", "missing-large-boxes", "missing-large-assets", "no-large-box-pairs"},
            )
            if decision.should_apply:
                self.assertEqual(decision.suggested_adjustments["global"]["dy"], 50)

    def test_analyze_global_asset_alignment_skips_when_shift_is_not_consistent(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reference_path = root / "reference.png"
            assets_dir = root / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            source_path = root / "source.png"

            reference = Image.new("RGB", (400, 240), (255, 255, 255))
            draw = ImageDraw.Draw(reference)
            draw.rounded_rectangle((40, 30, 180, 145), radius=8, outline=(0, 80, 220), width=3)
            draw.rounded_rectangle((220, 125, 360, 235), radius=8, outline=(0, 80, 220), width=3)
            reference.save(reference_path)

            asset_1 = Image.new("RGBA", (140, 115), (255, 255, 255, 0))
            draw_1 = ImageDraw.Draw(asset_1)
            draw_1.rounded_rectangle((0, 0, 139, 114), radius=8, outline=(0, 80, 220, 255), width=3)
            asset_1.save(assets_dir / "asset_001.png")

            asset_2 = Image.new("RGBA", (140, 115), (255, 255, 255, 0))
            draw_2 = ImageDraw.Draw(asset_2)
            draw_2.rounded_rectangle((0, 0, 139, 114), radius=8, outline=(0, 80, 220, 255), width=3)
            asset_2.save(assets_dir / "asset_002.png")

            Image.new("RGBA", (400, 240), (255, 255, 255, 0)).save(source_path)
            manifest_path = assets_dir / "assets.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "source_image": str(source_path),
                        "image_width": 400,
                        "image_height": 240,
                        "assets": [
                            {"index": 1, "file": "asset_001.png", "left": 40, "top": 20, "width": 140, "height": 115},
                            {"index": 2, "file": "asset_002.png", "left": 220, "top": 20, "width": 140, "height": 115},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            decision = analyze_global_asset_alignment(
                reference_image=reference_path,
                manifest_path=manifest_path,
                page_script="",
                current_adjustments={},
                min_shift_px=12,
                max_spread_px=20,
                max_center_gap=140,
            )

            self.assertFalse(decision.should_apply)
            self.assertIn(
                decision.reason,
                {
                    "inconsistent-global-shift",
                    "iou-and-center-gain-too-small",
                    "missing-large-boxes",
                    "missing-large-assets",
                    "no-large-box-pairs",
                },
            )

    def test_analyze_global_asset_alignment_uses_center_reward_for_large_frame_page(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reference_path = root / "reference.png"
            assets_dir = root / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            source_path = root / "source.png"

            reference = Image.new("RGB", (400, 240), (255, 255, 255))
            draw = ImageDraw.Draw(reference)
            draw.rounded_rectangle((60, 70, 340, 200), radius=10, outline=(0, 80, 220), width=3)
            reference.save(reference_path)

            asset = Image.new("RGBA", (280, 130), (255, 255, 255, 0))
            draw_asset = ImageDraw.Draw(asset)
            draw_asset.rounded_rectangle((0, 0, 279, 129), radius=10, outline=(0, 80, 220, 255), width=3)
            asset.save(assets_dir / "asset_001.png")

            Image.new("RGBA", (400, 240), (255, 255, 255, 0)).save(source_path)
            manifest_path = assets_dir / "assets.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "source_image": str(source_path),
                        "image_width": 400,
                        "image_height": 240,
                        "assets": [
                            {"index": 1, "file": "asset_001.png", "left": 60, "top": 30, "width": 280, "height": 130}
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            decision = analyze_global_asset_alignment(
                reference_image=reference_path,
                manifest_path=manifest_path,
                page_script='add_text(slide, "标题", 120, 115, 160, 32, size=20)',
                current_adjustments={},
                min_shift_px=8,
            )

            self.assertTrue(decision.should_apply)
            self.assertEqual(decision.suggested_adjustments["global"]["dy"], 40)


if __name__ == "__main__":
    unittest.main()
