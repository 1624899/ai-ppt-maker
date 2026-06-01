from __future__ import annotations

import unittest

from ppt_system.export.text_script_runtime import normalize_page_script


class TextScriptEmptyContentTests(unittest.TestCase):
    def test_normalize_page_script_skips_empty_center_text_call(self) -> None:
        script = 'add_center_text(slide, "", 0, 4, 2048, 1089, size=72, color="A3A5BA", bold=True, anchor="TOP")'

        self.assertEqual(normalize_page_script(script), "")

    def test_normalize_page_script_skips_whitespace_text_call(self) -> None:
        script = 'add_text(slide, "   ", 10, 20, 200, 60, size=24, color="163A63")'

        self.assertEqual(normalize_page_script(script), "")

    def test_normalize_page_script_filters_empty_runs_and_keeps_content_runs(self) -> None:
        script = (
            'add_runs(slide, [{"text":"","size":64,"color":"08265C"},'
            '{"text":"   ","size":64,"color":"08265C"},'
            '{"text":null,"size":64,"color":"08265C"},'
            '{"text":"标题","size":64,"color":"08265C","bold":true}],'
            '100, 120, 500, 90, align="LEFT", anchor="TOP")'
        )
        expected = (
            'add_runs(slide, [{"text": "标题", "size": 64, "color": "08265C", "bold": True}], '
            '100, 120, 500, 90, align="LEFT", anchor="TOP")'
        )

        self.assertEqual(normalize_page_script(script), expected)

    def test_normalize_page_script_skips_runs_when_all_items_are_empty(self) -> None:
        script = 'add_runs(slide, [{"text":"","size":64},{"text":"   ","size":64}], 100, 120, 500, 90)'

        self.assertEqual(normalize_page_script(script), "")

    def test_normalize_page_script_keeps_strict_validation_for_non_content_fields(self) -> None:
        script = 'add_text(slide, "标题", 10, 20, 200, 60, size=24, color="")'

        with self.assertRaises(RuntimeError):
            normalize_page_script(script)


if __name__ == "__main__":
    unittest.main()
