from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw

from ppt_system.image.text_placeholder_detection import detect_text_placeholders, placeholder_bboxes, save_text_placeholders


class TextPlaceholderDetectionTests(unittest.TestCase):
    def test_detects_placeholder_boxes_from_reference_minus_elements(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reference_path = root / "reference.png"
            elements_path = root / "elements.png"
            output_path = root / "text_placeholders.json"

            reference = Image.new("RGBA", (420, 240), (255, 255, 255, 255))
            elements = Image.new("RGBA", (420, 240), (255, 255, 255, 255))
            draw_reference = ImageDraw.Draw(reference)
            draw_elements = ImageDraw.Draw(elements)
            draw_reference.rounded_rectangle((260, 42, 374, 104), radius=8, fill=(236, 246, 255, 255))
            draw_elements.rounded_rectangle((260, 42, 374, 104), radius=8, fill=(236, 246, 255, 255))

            # 用多段矩形模拟中文/英文笔画，验证算法依赖差异区域而不是特定文字内容。
            draw_reference.rectangle((34, 30, 72, 38), fill=(18, 58, 99, 255))
            draw_reference.rectangle((80, 30, 136, 38), fill=(18, 58, 99, 255))
            draw_reference.rectangle((38, 118, 88, 126), fill=(72, 84, 96, 255))
            draw_reference.rectangle((38, 139, 122, 147), fill=(72, 84, 96, 255))
            reference.save(reference_path)
            elements.save(elements_path)

            result = save_text_placeholders(reference_path, elements_path, output_path)

            self.assertTrue(output_path.exists())
            placeholders = result["placeholders"]
            self.assertGreaterEqual(len(placeholders), 2)
            first = placeholders[0]
            second = placeholders[1]
            self.assertLess(first["left"], 40)
            self.assertLess(first["top"], 32)
            self.assertEqual(first["color"], "123A63")
            self.assertEqual(second["line_count"], 2)
            self.assertEqual(second["color"], "485460")
            self.assertEqual(placeholder_bboxes(result)[0][2], first["width"])

    def test_detection_generalizes_when_text_regions_shift(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            boxes: list[tuple[int, int, int, int]] = []
            for index, offset in enumerate((0, 28), start=1):
                reference_path = root / f"reference_{index}.png"
                elements_path = root / f"elements_{index}.png"
                reference = Image.new("RGBA", (360, 180), (255, 255, 255, 255))
                elements = Image.new("RGBA", (360, 180), (255, 255, 255, 255))
                draw_reference = ImageDraw.Draw(reference)
                draw_reference.rectangle((42 + offset, 72, 98 + offset, 80), fill=(30, 90, 160, 255))
                draw_reference.rectangle((106 + offset, 72, 152 + offset, 80), fill=(30, 90, 160, 255))
                reference.save(reference_path)
                elements.save(elements_path)

                result = detect_text_placeholders(reference_path, elements_path)
                self.assertEqual(len(result["placeholders"]), 1)
                item = result["placeholders"][0]
                boxes.append((item["left"], item["top"], item["width"], item["height"]))

            self.assertGreater(boxes[1][0], boxes[0][0])
            self.assertAlmostEqual(boxes[1][0] - boxes[0][0], 28, delta=6)


if __name__ == "__main__":
    unittest.main()
