from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from ppt_system.image.canvas_normalization import ensure_image_canvas_size, normalize_image_canvas


class CanvasNormalizationTests(unittest.TestCase):
    def test_auto_resize_stretches_when_aspect_ratio_matches(self) -> None:
        with TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source.png"
            output = Path(tmpdir) / "output.png"
            Image.new("RGBA", (160, 90), (32, 96, 192, 255)).save(source)

            result = normalize_image_canvas(source, output, target_width=320, target_height=180)

            self.assertTrue(result.normalized)
            self.assertEqual(result.applied_resize_mode, "stretch")
            with Image.open(output) as image:
                self.assertEqual(image.size, (320, 180))
                self.assertEqual(image.convert("RGBA").getpixel((0, 0)), (32, 96, 192, 255))

    def test_auto_resize_contains_when_aspect_ratio_differs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "square.png"
            output = Path(tmpdir) / "wide.png"
            Image.new("RGBA", (100, 100), (224, 64, 32, 255)).save(source)

            result = normalize_image_canvas(source, output, target_width=200, target_height=100)

            self.assertTrue(result.normalized)
            self.assertEqual(result.applied_resize_mode, "contain")
            with Image.open(output) as image:
                pixels = image.convert("RGBA")
                self.assertEqual(pixels.size, (200, 100))
                self.assertEqual(pixels.getpixel((0, 0)), (255, 255, 255, 255))
                self.assertEqual(pixels.getpixel((100, 50)), (224, 64, 32, 255))

    def test_auto_resize_preserves_transparent_canvas_when_source_has_alpha(self) -> None:
        with TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "transparent.png"
            output = Path(tmpdir) / "normalized.png"
            image = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
            image.paste((64, 192, 96, 255), (20, 20, 80, 80))
            image.save(source)

            normalize_image_canvas(source, output, target_width=200, target_height=100)

            with Image.open(output) as image:
                pixels = image.convert("RGBA")
                self.assertEqual(pixels.size, (200, 100))
                self.assertEqual(pixels.getpixel((0, 0))[3], 0)
                self.assertGreater(pixels.getpixel((100, 50))[3], 0)

    def test_ensure_image_canvas_size_skips_matching_image(self) -> None:
        with TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "page.png"
            Image.new("RGBA", (320, 180), (255, 255, 255, 255)).save(image_path)

            result = ensure_image_canvas_size(image_path, target_width=320, target_height=180)

            self.assertFalse(result.normalized)
            self.assertEqual(result.applied_resize_mode, "unchanged")
            with Image.open(image_path) as image:
                self.assertEqual(image.size, (320, 180))


if __name__ == "__main__":
    unittest.main()
