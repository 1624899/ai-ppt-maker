from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw

from ppt_system.image.global_element_alignment import align_elements_image_to_reference, analyze_global_element_alignment


class GlobalElementAlignmentTests(unittest.TestCase):
    def test_analyze_global_element_alignment_detects_stable_shift(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reference_path = root / "reference.png"
            elements_path = root / "elements.png"

            reference = Image.new("RGBA", (400, 240), (255, 255, 255, 255))
            draw_reference = ImageDraw.Draw(reference)
            draw_reference.rounded_rectangle((60, 50, 180, 150), radius=8, outline=(0, 80, 220, 255), width=4)
            draw_reference.rounded_rectangle((230, 80, 350, 190), radius=8, outline=(0, 80, 220, 255), width=4)
            reference.save(reference_path)

            elements = Image.new("RGBA", (400, 240), (255, 255, 255, 0))
            draw_elements = ImageDraw.Draw(elements)
            draw_elements.rounded_rectangle((48, 74, 168, 174), radius=8, outline=(0, 80, 220, 255), width=4)
            draw_elements.rounded_rectangle((218, 104, 338, 214), radius=8, outline=(0, 80, 220, 255), width=4)
            elements.save(elements_path)

            decision = analyze_global_element_alignment(
                reference_image=reference_path,
                elements_image=elements_path,
                min_shift_px=8,
                min_iou_gain=0.02,
            )

            self.assertTrue(decision.should_apply)
            self.assertEqual(decision.dx, 12)
            self.assertEqual(decision.dy, -24)
            self.assertEqual(decision.reason, "apply-global-element-shift")

    def test_analyze_global_element_alignment_uses_rgb_foreground_for_opaque_images(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reference_path = root / "reference.png"
            elements_path = root / "elements.png"

            reference = Image.new("RGB", (400, 240), (255, 255, 255))
            draw_reference = ImageDraw.Draw(reference)
            draw_reference.rounded_rectangle((80, 50, 180, 140), radius=8, outline=(0, 80, 220), width=4)
            draw_reference.rounded_rectangle((240, 80, 340, 180), radius=8, outline=(0, 80, 220), width=4)
            reference.save(reference_path)

            elements = Image.new("RGB", (400, 240), (255, 255, 255))
            draw_elements = ImageDraw.Draw(elements)
            draw_elements.rounded_rectangle((65, 68, 165, 158), radius=8, outline=(0, 80, 220), width=4)
            draw_elements.rounded_rectangle((225, 98, 325, 198), radius=8, outline=(0, 80, 220), width=4)
            elements.save(elements_path)

            decision = analyze_global_element_alignment(
                reference_image=reference_path,
                elements_image=elements_path,
                min_shift_px=8,
                min_iou_gain=0.02,
            )

            self.assertTrue(decision.should_apply)
            self.assertEqual(decision.dx, 15)
            self.assertEqual(decision.dy, -18)

    def test_analyze_global_element_alignment_rejects_page_scale_shift(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reference_path = root / "reference.png"
            elements_path = root / "elements.png"

            reference = Image.new("RGBA", (400, 240), (255, 255, 255, 255))
            draw_reference = ImageDraw.Draw(reference)
            draw_reference.rounded_rectangle((170, 70, 260, 160), radius=8, outline=(0, 80, 220, 255), width=4)
            reference.save(reference_path)

            elements = Image.new("RGBA", (400, 240), (255, 255, 255, 0))
            draw_elements = ImageDraw.Draw(elements)
            draw_elements.rounded_rectangle((70, 70, 160, 160), radius=8, outline=(0, 80, 220, 255), width=4)
            elements.save(elements_path)

            decision = analyze_global_element_alignment(
                reference_image=reference_path,
                elements_image=elements_path,
                min_shift_px=8,
                min_iou_gain=0.02,
                max_shift_ratio=0.1,
            )

            self.assertFalse(decision.should_apply)
            self.assertEqual(decision.reason, "shift-too-large")
            self.assertEqual(decision.dx, 100)
            self.assertEqual(decision.dy, 0)

    def test_align_elements_image_to_reference_writes_shifted_result(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reference_path = root / "reference.png"
            elements_path = root / "elements.png"
            output_path = root / "aligned.png"

            reference = Image.new("RGBA", (120, 80), (255, 255, 255, 255))
            draw_reference = ImageDraw.Draw(reference)
            draw_reference.rectangle((30, 20, 59, 49), fill=(0, 80, 220, 255))
            reference.save(reference_path)

            elements = Image.new("RGBA", (120, 80), (255, 255, 255, 0))
            draw_elements = ImageDraw.Draw(elements)
            draw_elements.rectangle((22, 29, 51, 58), fill=(0, 80, 220, 255))
            elements.save(elements_path)

            decision = align_elements_image_to_reference(
                reference_image=reference_path,
                elements_image=elements_path,
                output_path=output_path,
                min_shift_px=4,
                min_iou_gain=0.02,
            )

            self.assertTrue(decision.should_apply)
            self.assertTrue(output_path.exists())
            with Image.open(output_path).convert("RGBA") as aligned:
                self.assertEqual(aligned.getpixel((30, 20))[3], 255)
                self.assertEqual(aligned.getpixel((22, 29))[3], 0)

    def test_analyze_global_element_alignment_ignores_small_shift(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reference_path = root / "reference.png"
            elements_path = root / "elements.png"

            reference = Image.new("RGBA", (160, 100), (255, 255, 255, 255))
            draw_reference = ImageDraw.Draw(reference)
            draw_reference.rectangle((40, 20, 100, 60), fill=(0, 80, 220, 255))
            reference.save(reference_path)

            elements = Image.new("RGBA", (160, 100), (255, 255, 255, 0))
            draw_elements = ImageDraw.Draw(elements)
            draw_elements.rectangle((37, 23, 97, 63), fill=(0, 80, 220, 255))
            elements.save(elements_path)

            decision = analyze_global_element_alignment(
                reference_image=reference_path,
                elements_image=elements_path,
                min_shift_px=8,
                min_iou_gain=0.01,
            )

            self.assertFalse(decision.should_apply)
            self.assertEqual(decision.reason, "shift-too-small")


if __name__ == "__main__":
    unittest.main()
