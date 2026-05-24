from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image

from ppt_system.background_removal import remove_background
from ppt_system.image_ops import make_transparent


class BackgroundRemovalTests(unittest.TestCase):
    def test_preserve_existing_alpha_without_invoking_rembg(self) -> None:
        image = Image.new("RGBA", (2, 1))
        image.putpixel((0, 0), (255, 255, 255, 0))
        image.putpixel((1, 0), (10, 20, 30, 255))

        result = remove_background(image)

        self.assertEqual(result.strategy, "preserve-alpha")
        self.assertIsNone(result.warning)
        self.assertEqual(result.image.getpixel((0, 0)), (255, 255, 255, 0))
        self.assertEqual(result.image.getpixel((1, 0)), (10, 20, 30, 255))

    @patch("ppt_system.background_removal._load_rembg_remove")
    def test_runtime_failure_falls_back_to_threshold_strategy(self, mock_loader) -> None:
        def broken_remove(_image: Image.Image) -> Image.Image:
            raise RuntimeError("model download failed")

        mock_loader.return_value = broken_remove
        image = Image.new("RGBA", (2, 1))
        image.putpixel((0, 0), (255, 255, 255, 255))
        image.putpixel((1, 0), (10, 20, 30, 255))

        result = remove_background(image, fallback_bg_threshold=245)

        self.assertEqual(result.strategy, "threshold")
        self.assertIn("rembg 运行失败", result.warning or "")
        self.assertEqual(result.image.getpixel((0, 0)), (255, 255, 255, 0))
        self.assertEqual(result.image.getpixel((1, 0)), (10, 20, 30, 255))

    @patch("ppt_system.background_removal._load_rembg_remove", return_value=None)
    def test_make_transparent_returns_warning_metadata_when_rembg_missing(self, _mock_loader) -> None:
        with TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.png"
            image = Image.new("RGBA", (1, 1), (255, 255, 255, 255))
            image.save(input_path)

            result = make_transparent(input_path, output_path)

            self.assertTrue(output_path.exists())
            self.assertEqual(result.output_path, output_path)
            self.assertEqual(result.strategy, "threshold")
            self.assertIn("未安装 rembg", result.warning or "")

    @patch("ppt_system.background_removal._load_rembg_remove", return_value=None)
    def test_threshold_fallback_preserves_inner_white_region_when_not_border_connected(self, _mock_loader) -> None:
        image = Image.new("RGBA", (7, 7), (255, 255, 255, 255))
        pixels = image.load()
        for x in range(1, 6):
            pixels[x, 1] = (0, 0, 0, 255)
            pixels[x, 5] = (0, 0, 0, 255)
        for y in range(1, 6):
            pixels[1, y] = (0, 0, 0, 255)
            pixels[5, y] = (0, 0, 0, 255)

        result = remove_background(image, fallback_bg_threshold=245)

        self.assertEqual(result.strategy, "threshold")
        self.assertEqual(result.image.getpixel((0, 0))[3], 0)
        self.assertEqual(result.image.getpixel((3, 3))[3], 255)


if __name__ == "__main__":
    unittest.main()
