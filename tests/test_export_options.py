from __future__ import annotations

import unittest

from web_app import build_export_options


class ExportOptionsTests(unittest.TestCase):
    def test_reads_page_export_concurrency_with_safe_minimum(self) -> None:
        options = build_export_options({"export_page_concurrency": 0})

        self.assertEqual(options["export_page_concurrency"], 1)

    def test_reads_positive_page_export_concurrency(self) -> None:
        options = build_export_options({"export_page_concurrency": 3})

        self.assertEqual(options["export_page_concurrency"], 3)


if __name__ == "__main__":
    unittest.main()
