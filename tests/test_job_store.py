from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ppt_system.jobs.job_store import create_job, get_job, init_db, update_job


class JobStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = Path(self.temp_dir.name) / "jobs.sqlite3"
        init_db(self.db_path)
        create_job(
            self.db_path,
            {
                "job_id": "job-store-demo",
                "status": "queued",
                "current_stage": "queued",
                "title": "旧标题",
                "content": "测试内容",
                "page_count": 1,
                "image_preset": "landscape_2k",
                "image_quality": "medium",
                "style_notes": "",
                "job_dir": str(Path(self.temp_dir.name) / "job-store-demo"),
                "request": {},
                "state": {},
                "result": {},
                "stop_requested": False,
            },
        )

    def test_update_job_allows_known_columns(self) -> None:
        update_job(self.db_path, "job-store-demo", title="新标题", stop_requested=True)

        record = get_job(self.db_path, "job-store-demo")

        self.assertIsNotNone(record)
        self.assertEqual(record["title"], "新标题")
        self.assertTrue(record["stop_requested"])

    def test_update_job_rejects_unknown_columns(self) -> None:
        with self.assertRaisesRegex(ValueError, "不支持更新任务字段"):
            update_job(self.db_path, "job-store-demo", **{"title = 'bad' --": "x"})

        record = get_job(self.db_path, "job-store-demo")
        self.assertIsNotNone(record)
        self.assertEqual(record["title"], "旧标题")


if __name__ == "__main__":
    unittest.main()
