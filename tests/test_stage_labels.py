from __future__ import annotations

import unittest

from ppt_system.export.stage_labels import get_stage_label, normalize_stage_label


class StageLabelTests(unittest.TestCase):
    def test_get_stage_label_returns_builtin_mapping(self) -> None:
        self.assertEqual(get_stage_label("planning"), "模型规划")
        self.assertEqual(get_stage_label("ppt_export"), "可编辑元素生成")

    def test_normalize_stage_label_replaces_question_marks(self) -> None:
        self.assertEqual(normalize_stage_label("planning", "????"), "模型规划")
        self.assertEqual(normalize_stage_label("ppt_export", "PPT ??"), "可编辑元素生成")

    def test_normalize_stage_label_falls_back_when_missing(self) -> None:
        self.assertEqual(normalize_stage_label("elements_generation", ""), "元素图生成")


if __name__ == "__main__":
    unittest.main()
