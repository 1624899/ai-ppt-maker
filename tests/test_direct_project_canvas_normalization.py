from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from ppt_system.export.direct_project_script import prepare_direct_project_assets


class DirectProjectCanvasNormalizationTests(unittest.TestCase):
    def test_prepare_assets_uses_declared_project_canvas(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            reference = root / "reference.png"
            elements = root / "elements.png"
            Image.new("RGBA", (50, 50), (255, 255, 255, 255)).save(reference)
            Image.new("RGBA", (40, 30), (64, 128, 192, 255)).save(elements)
            project = {
                "slide_width_inch": 13.333333,
                "image_width": 80,
                "image_height": 45,
                "pages": [
                    {
                        "page_no": 1,
                        "reference_image": str(reference),
                        "visual_image": str(elements),
                    }
                ],
            }

            result = prepare_direct_project_assets(
                project,
                root / "work",
                skip_enhance=True,
                skip_transparent=True,
                min_area=1,
                merge_distance=0,
            )

            with Image.open(reference) as reference_image:
                self.assertEqual(reference_image.size, (80, 45))
            with Image.open(elements) as elements_image:
                self.assertEqual(elements_image.size, (80, 45))

        prepared = result["prepared_assets_by_page"][1]
        self.assertEqual(prepared.image_width, 80)
        self.assertEqual(prepared.image_height, 45)


if __name__ == "__main__":
    unittest.main()
