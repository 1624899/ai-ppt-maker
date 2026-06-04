from __future__ import annotations

import unittest

from ppt_system.generation.design_grammar import (
    ALLOWED_LAYOUT_FAMILIES,
    DEFAULT_LAYOUT_FAMILIES,
    LAYOUT_FAMILY_LABELS,
    build_layout_family_options,
    normalize_layout_family_name,
)
from ppt_system.generation.text_layout import (
    build_fallback_boxes_for_family,
    build_layout_slots_by_family,
    list_supported_layout_slot_families,
)


class LayoutFamilyRegistryTests(unittest.TestCase):
    def test_layout_family_options_cover_registered_families(self) -> None:
        options = build_layout_family_options()

        self.assertEqual({item["value"] for item in options}, ALLOWED_LAYOUT_FAMILIES)
        self.assertEqual(set(DEFAULT_LAYOUT_FAMILIES), ALLOWED_LAYOUT_FAMILIES)
        for item in options:
            self.assertIn(item["value"], LAYOUT_FAMILY_LABELS)
            self.assertNotEqual(item["label"], item["value"])

    def test_registered_layout_families_have_slot_templates(self) -> None:
        self.assertEqual(list_supported_layout_slot_families(), ALLOWED_LAYOUT_FAMILIES)

        for family in ALLOWED_LAYOUT_FAMILIES:
            slots = build_layout_slots_by_family(family, 2048, 1152)
            self.assertEqual(slots["family"], family)
            self.assertGreaterEqual(len(slots["slot_coords"]), 2)

    def test_unknown_or_special_layout_families_normalize_before_use(self) -> None:
        self.assertEqual(normalize_layout_family_name("左右对照"), "compare_dual_axis")
        self.assertEqual(normalize_layout_family_name("双轴对比"), "compare_dual_axis")
        self.assertEqual(normalize_layout_family_name("hero_with_supporting_cards_2"), "hero_with_supporting_cards")

        fallback = build_layout_slots_by_family("尚未注册的特殊版式", 2048, 1152)
        self.assertEqual(fallback["family"], "split_left_right")

    def test_compare_dual_axis_uses_dedicated_fallback_boxes(self) -> None:
        boxes = build_fallback_boxes_for_family(
            "compare_dual_axis",
            "方案对比",
            "• 成本\n• 效率\n• 风险",
            2048,
            1152,
        )

        self.assertEqual(len(boxes), 4)
        self.assertEqual([box["role"] for box in boxes], ["title", "body", "body", "body"])
        self.assertLess(boxes[1]["left"], boxes[2]["left"])


if __name__ == "__main__":
    unittest.main()
