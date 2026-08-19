from __future__ import annotations

import unittest

from ppt_system.generation.design_grammar import DEFAULT_LAYOUT_FAMILIES
from ppt_system.generation.layout_blueprint_catalog import FACTORIES, build_blueprint
from ppt_system.generation.layout_geometry import build_layout_slot_specs


class LayoutBlueprintCatalogTests(unittest.TestCase):
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
