from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from ppt_system.jobs.job_store import create_job as create_job_record
from ppt_system.jobs.job_store import get_job as get_job_record
from ppt_system.jobs.job_store import init_db as init_job_db
from ppt_system.jobs.job_store import update_job as update_job_record


class JobManageApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base_dir = Path(self.temp_dir.name)
        self.jobs_db_path = self.base_dir / "jobs.sqlite3"
        init_job_db(self.jobs_db_path)
        self.output_dir = self.base_dir / "runs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config = {"output_dir": str(self.output_dir)}
        self.read_config_patch = patch.object(main, "read_config", return_value=self.config)
        self.jobs_db_patch = patch.object(main, "JOBS_DB_PATH", self.jobs_db_path)
        self.read_config_patch.start()
        self.jobs_db_patch.start()
        self.addCleanup(self.read_config_patch.stop)
        self.addCleanup(self.jobs_db_patch.stop)
        main.JOB_STATUS_CACHE.clear()
        self.client = main.app.test_client()

    def _create_record(
        self,
        job_id: str,
        *,
        title: str,
        status: str = "completed",
        stop_requested: bool = False,
        updated_at: str | None = None,
    ) -> Path:
        job_dir = self.output_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        state = {
            "job_id": job_id,
            "status": status,
            "current_stage": "ppt_export",
            "stop_requested": stop_requested,
            "pages": [],
            "stages": [
                {"key": "ppt_export", "status": status, "summary": "", "logs": []},
            ],
        }
        (job_dir / "status.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        create_job_record(
            self.jobs_db_path,
            {
                "job_id": job_id,
                "status": status,
                "current_stage": "ppt_export",
                "title": title,
                "content": title,
                "page_count": 1,
                "image_preset": "landscape_2k",
                "image_quality": "medium",
                "style_notes": "",
                "job_dir": str(job_dir),
                "request": {},
                "state": state,
                "result": {},
                "stop_requested": stop_requested,
            },
        )
        if updated_at:
            update_job_record(self.jobs_db_path, job_id, touch_updated_at=False, updated_at=updated_at)
        return job_dir

    def test_rename_job_updates_history_summary_and_detail_title(self) -> None:
        self._create_record("job-rename-demo", title="旧标题")

        response = self.client.patch("/api/jobs/job-rename-demo", json={"action": "rename", "title": "新标题"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["title"], "新标题")
        record = get_job_record(self.jobs_db_path, "job-rename-demo")
        self.assertIsNotNone(record)
        self.assertEqual(record["title"], "新标题")

        detail_response = self.client.get("/api/jobs/job-rename-demo")
        detail = detail_response.get_json()
        self.assertEqual(detail["title"], "新标题")

    def test_pin_job_sets_pinned_at_without_changing_history_order(self) -> None:
        self._create_record("job-old", title="旧任务")
        self._create_record("job-pin", title="待置顶")
        update_job_record(self.jobs_db_path, "job-old", touch_updated_at=False, updated_at="2026-01-01 00:00:01.000")
        update_job_record(self.jobs_db_path, "job-pin", touch_updated_at=False, updated_at="2026-01-01 00:00:02.000")

        response = self.client.patch("/api/jobs/job-old", json={"action": "pin"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["pinned_at"])
        history = self.client.get("/api/jobs").get_json()
        self.assertEqual(history["items"][0]["job_id"], "job-pin")
        pinned = next(item for item in history["items"] if item["job_id"] == "job-old")
        self.assertTrue(pinned["pinned_at"])

    def test_unpin_job_clears_pinned_at_without_touching_history_order(self) -> None:
        self._create_record("job-old", title="旧任务")
        self._create_record("job-pin", title="待取消置顶")
        update_job_record(
            self.jobs_db_path,
            "job-pin",
            touch_updated_at=False,
            pinned_at="2026-01-02 00:00:00.000",
            updated_at="2026-01-01 00:00:01.000",
        )
        update_job_record(self.jobs_db_path, "job-old", touch_updated_at=False, updated_at="2026-01-01 00:00:02.000")

        response = self.client.patch("/api/jobs/job-pin", json={"action": "unpin"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["pinned_at"], "")
        history = self.client.get("/api/jobs").get_json()
        self.assertEqual(history["items"][0]["job_id"], "job-old")

    def test_delete_job_removes_record_and_artifacts_for_finished_job(self) -> None:
        job_dir = self._create_record("job-delete-demo", title="可删除任务")
        (job_dir / "artifact.txt").write_text("demo", encoding="utf-8")

        response = self.client.delete("/api/jobs/job-delete-demo")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(get_job_record(self.jobs_db_path, "job-delete-demo"))
        self.assertFalse(job_dir.exists())

    def test_delete_job_rejects_running_status(self) -> None:
        job_dir = self._create_record("job-running-demo", title="运行中任务", status="running")

        response = self.client.delete("/api/jobs/job-running-demo")

        self.assertEqual(response.status_code, 400)
        self.assertIsNotNone(get_job_record(self.jobs_db_path, "job-running-demo"))
        self.assertTrue(job_dir.exists())

    def test_delete_job_allows_stale_stopping_job_after_archiving(self) -> None:
        job_dir = self._create_record(
            "job-stale-stopping-demo",
            title="陈旧暂停任务",
            status="stopping",
            stop_requested=True,
            updated_at="2026-01-01 00:00:01.000",
        )

        response = self.client.delete("/api/jobs/job-stale-stopping-demo")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(get_job_record(self.jobs_db_path, "job-stale-stopping-demo"))
        self.assertFalse(job_dir.exists())


if __name__ == "__main__":
    unittest.main()
