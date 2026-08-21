from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from ppt_system.jobs.job_store import create_job, get_job, init_db, reconcile_job_directories, update_job


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

    def test_job_directory_is_persisted_as_portable_reference(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            stored_job_dir = conn.execute(
                "SELECT job_dir FROM jobs WHERE job_id = ?",
                ("job-store-demo",),
            ).fetchone()[0]

        record = get_job(self.db_path, "job-store-demo")

        self.assertEqual(stored_job_dir, "job-store-demo")
        self.assertIsNotNone(record)
        self.assertEqual(record["job_dir"], str((Path(self.temp_dir.name) / "job-store-demo").resolve()))

    def test_job_directory_resolves_after_data_is_moved_to_another_user_root(self) -> None:
        base_dir = Path(self.temp_dir.name)
        source_data_dir = base_dir / "source-user" / "AI PPT Maker"
        source_output_dir = source_data_dir / "output"
        source_db_path = source_output_dir / "jobs.sqlite3"
        source_job_dir = source_output_dir / "portable-job"
        source_job_dir.mkdir(parents=True)
        init_db(source_db_path)
        create_job(source_db_path, self._job_payload("portable-job", source_job_dir))

        target_data_dir = base_dir / "target-user" / "AI PPT Maker"
        target_output_dir = target_data_dir / "output"
        shutil.copytree(source_output_dir, target_output_dir)
        target_db_path = target_output_dir / "jobs.sqlite3"
        init_db(target_db_path)

        record = get_job(target_db_path, "portable-job")

        self.assertIsNotNone(record)
        self.assertEqual(record["job_dir"], str((target_output_dir / "portable-job").resolve()))

    def test_init_db_converts_stale_absolute_job_directory_once(self) -> None:
        data_dir = Path(self.temp_dir.name) / "current-user" / "AI PPT Maker"
        output_dir = data_dir / "output"
        db_path = output_dir / "jobs.sqlite3"
        current_job_dir = output_dir / "legacy-job"
        current_job_dir.mkdir(parents=True)
        init_db(db_path)
        create_job(db_path, self._job_payload("legacy-job", current_job_dir))
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE jobs SET job_dir = ? WHERE job_id = ?",
                ("C:/Users/old-user/AppData/Roaming/AI PPT Maker/output/legacy-job", "legacy-job"),
            )

        init_db(db_path)

        with sqlite3.connect(db_path) as conn:
            stored_job_dir = conn.execute(
                "SELECT job_dir FROM jobs WHERE job_id = ?",
                ("legacy-job",),
            ).fetchone()[0]
        record = get_job(db_path, "legacy-job")
        self.assertEqual(stored_job_dir, "legacy-job")
        self.assertIsNotNone(record)
        self.assertEqual(record["job_dir"], str(current_job_dir.resolve()))

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

    def test_reconcile_job_directories_moves_only_missing_paths(self) -> None:
        output_root = Path(self.temp_dir.name) / "appdata-output"
        target = output_root / "job-store-demo"
        target.mkdir(parents=True)

        changed = reconcile_job_directories(self.db_path, output_root)

        self.assertEqual(changed, 1)
        self.assertEqual(get_job(self.db_path, "job-store-demo")["job_dir"], str(target.resolve()))

    @staticmethod
    def _job_payload(job_id: str, job_dir: Path) -> dict:
        return {
            "job_id": job_id,
            "status": "queued",
            "current_stage": "queued",
            "title": "路径测试",
            "content": "测试内容",
            "page_count": 1,
            "image_preset": "landscape_2k",
            "image_quality": "medium",
            "style_notes": "",
            "job_dir": str(job_dir),
            "request": {},
            "state": {},
            "result": {},
            "stop_requested": False,
        }


if __name__ == "__main__":
    unittest.main()
