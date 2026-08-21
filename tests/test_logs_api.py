from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ppt_system.web.services import logs_api_service


class LogsApiServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))
        patcher = mock.patch.object(logs_api_service.runtime_context, "LOGS_DIR", self.temp_dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_list_log_files_only_returns_app_logs(self) -> None:
        (self.temp_dir / "app-20260821.log").write_text("行1\n行2\n", encoding="utf-8")
        (self.temp_dir / "app-bad.log").write_text("不应列出\n", encoding="utf-8")
        (self.temp_dir / "other.txt").write_text("不应列出\n", encoding="utf-8")
        (self.temp_dir / "app-20260820.log").write_text("旧日志\n", encoding="utf-8")

        files = logs_api_service.list_log_files()

        self.assertEqual([item["name"] for item in files], ["app-20260821.log", "app-20260820.log"])

    def test_list_log_files_when_dir_missing(self) -> None:
        self.assertEqual(logs_api_service.list_log_files(), [])

    def test_read_log_tail_returns_last_lines(self) -> None:
        log_file = self.temp_dir / "app-20260821.log"
        log_file.write_text("".join(f"第{i}行\n" for i in range(1, 11)), encoding="utf-8")

        payload = logs_api_service.read_log_tail("app-20260821.log", 3)

        self.assertEqual(payload["lines"], ["第8行", "第9行", "第10行"])

    def test_read_log_tail_caps_lines(self) -> None:
        log_file = self.temp_dir / "app-20260821.log"
        log_file.write_text("".join(f"第{i}行\n" for i in range(1, 21)), encoding="utf-8")

        payload = logs_api_service.read_log_tail("app-20260821.log", 99999)

        self.assertEqual(len(payload["lines"]), 20)

    def test_read_log_rejects_path_traversal(self) -> None:
        with self.assertRaises(ValueError):
            logs_api_service.read_log_tail("../secret.log")

    def test_read_log_missing_file(self) -> None:
        with self.assertRaises(FileNotFoundError):
            logs_api_service.read_log_tail("app-20260821.log")


if __name__ == "__main__":
    unittest.main()
