from __future__ import annotations

import copy
import unittest

from ppt_system.web.services.page_text_style_ops import apply_page_text_layer_edit


class PageTextStyleOpsTests(unittest.TestCase):
    def setUp(self):
        self.page = {
            "reference_image": "/runs/job/reference.png",
            "element_image": "/runs/job/element.png",
            "texts": [{"text": "标题", "font_name": "Arial", "color": "000000", "align": "CENTER"}],
        }

    def test_font_and_color_preserve_images(self):
        images = {key: copy.deepcopy(self.page[key]) for key in ("reference_image", "element_image")}
        apply_page_text_layer_edit(self.page, "page_text_style", {"style": {"font_name": "Microsoft YaHei", "color": "163A63"}})
        self.assertEqual(self.page["reference_image"], images["reference_image"])
        self.assertEqual(self.page["element_image"], images["element_image"])
        self.assertEqual(self.page["texts"][0]["font_name"], "Microsoft YaHei")
        self.assertEqual(self.page["texts"][0]["color"], "163A63")

    def test_alignment_preserves_images(self):
        apply_page_text_layer_edit(self.page, "page_align", {"align": "LEFT"})
        self.assertEqual(self.page["reference_image"], "/runs/job/reference.png")
        self.assertEqual(self.page["element_image"], "/runs/job/element.png")
        self.assertEqual(self.page["texts"][0]["align"], "LEFT")


if __name__ == "__main__":
    unittest.main()
