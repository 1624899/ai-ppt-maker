from __future__ import annotations

import unittest

from ppt_system.generation.design_grammar import DEFAULT_LAYOUT_FAMILIES
from ppt_system.generation.layout_blueprint_catalog import FACTORIES, build_blueprint
from ppt_system.generation.layout_geometry import build_layout_slot_specs
from ppt_system.generation.text_layout import build_layout_slots_by_family, build_text_boxes_from_slots


class LayoutBlueprintCatalogTests(unittest.TestCase):
    def test_unknown_layout_uses_supported_slot_geometry(self):
        slots = build_layout_slots_by_family("historical-custom-layout", 2000, 1125)

        self.assertEqual(slots["family"], "split_left_right")
        self.assertIn("title", slots["slot_coords"])

    def test_multiple_text_slots_distribute_body_content(self):
        slots = build_layout_slots_by_family("grid_n_x_m", 2000, 1125)
        boxes = build_text_boxes_from_slots(slots, "标题", "甲\n乙\n丙\n丁", 2000, 1125)
        body_texts = [box["text"] for box in boxes if box["role"] == "body"]

        self.assertEqual(body_texts, ["甲", "乙", "丙", "丁"])

    def test_every_layout_has_a_blueprint(self):
        self.assertEqual(set(DEFAULT_LAYOUT_FAMILIES), set(FACTORIES))

    def test_every_layout_blueprint_is_unique(self):
        signatures = {
            family: tuple((item["kind"], item["label"], item["left"], item["top"], item["width"], item["height"]) for item in build_blueprint(family))
            for family in DEFAULT_LAYOUT_FAMILIES
        }
        self.assertEqual(len(signatures), len(set(signatures.values())))

    def test_blueprint_content_shapes_become_real_slots(self):
        for family in DEFAULT_LAYOUT_FAMILIES:
            expected = sum(not bool(item.get("decorative")) for item in build_blueprint(family))
            specs = build_layout_slot_specs(family, 2000, 1125)
            self.assertEqual(expected, len(specs), family)


if __name__ == "__main__":
    unittest.main()
