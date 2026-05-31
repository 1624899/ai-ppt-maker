from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from ppt_system.jobs.active_job_registry import clear_job_management_registry, mark_job_managed
from ppt_system.jobs.job_store import create_job as create_job_record
from ppt_system.jobs.job_store import init_db as init_job_db
from ppt_system.jobs.job_store import list_jobs as list_job_records


class JobDbMaintenanceApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.addCleanup(clear_job_management_registry)
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
        pinned_at: str = "",
        updated_at: str | None = None,
    ) -> Path:
        job_dir = self.output_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "artifact.txt").write_text(job_id, encoding="utf-8")
        state = {
            "job_id": job_id,
            "status": status,
            "current_stage": "ppt_export",
            "pages": [],
            "stages": [],
        }
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
                "stop_requested": False,
            },
        )
        if pinned_at or updated_at:
            fields: dict[str, str] = {}
            if pinned_at:
                fields["pinned_at"] = pinned_at
            if updated_at:
                fields["updated_at"] = updated_at
            main.update_job_record(self.jobs_db_path, job_id, touch_updated_at=False, **fields)
        return job_dir

    def test_job_db_stats_reports_counts(self) -> None:
        self._create_record("job-completed", title="完成任务", updated_at="2026-01-01 00:00:01.000")
        self._create_record("job-running", title="运行任务", status="running", updated_at="2026-01-01 00:00:02.000")
        self._create_record(
            "job-pinned",
            title="置顶任务",
            pinned_at="2026-01-01 00:00:03.000",
            updated_at="2026-01-01 00:00:03.000",
        )

        response = self.client.get("/api/jobs/db")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["exists"])
        self.assertEqual(payload["job_count"], 3)
        self.assertEqual(payload["pinned_job_count"], 1)
        self.assertEqual(payload["running_job_count"], 1)
        self.assertGreaterEqual(payload["size_bytes"], 0)

    def test_job_db_maintenance_dry_run_keeps_records_and_lists_candidates(self) -> None:
        self._create_record("job-1", title="任务1", updated_at="2026-01-01 00:00:01.000")
        self._create_record("job-2", title="任务2", updated_at="2026-01-01 00:00:02.000")
        self._create_record("job-3", title="任务3", updated_at="2026-01-01 00:00:03.000")

        response = self.client.post(
            "/api/jobs/db/maintenance",
            json={"keep_latest": 1, "dry_run": True},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["candidate_count"], 2)
        self.assertEqual(payload["deleted_count"], 0)
        self.assertEqual(len(list_job_records(self.jobs_db_path, limit=None)), 3)

    def test_job_db_maintenance_deletes_old_finished_jobs_and_artifacts(self) -> None:
        old_dir = self._create_record("job-old", title="旧任务", updated_at="2026-01-01 00:00:01.000")
        self._create_record("job-new", title="新任务", updated_at="2026-01-01 00:00:03.000")
        self._create_record(
            "job-pinned",
            title="置顶任务",
            pinned_at="2026-01-01 00:00:04.000",
            updated_at="2026-01-01 00:00:02.000",
        )

        response = self.client.post(
            "/api/jobs/db/maintenance",
            json={"keep_latest": 1, "dry_run": False},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["deleted_count"], 1)
        self.assertEqual(payload["deleted_job_ids"], ["job-old"])
        self.assertFalse(old_dir.exists())
        remaining_ids = [item["job_id"] for item in list_job_records(self.jobs_db_path, limit=None)]
        self.assertEqual(set(remaining_ids), {"job-new", "job-pinned"})

    def test_job_db_maintenance_skips_managed_jobs(self) -> None:
        managed_dir = self._create_record("job-managed", title="托管任务", updated_at="2026-01-01 00:00:01.000")
        self._create_record("job-new", title="新任务", updated_at="2026-01-01 00:00:03.000")
        mark_job_managed("job-managed")

        response = self.client.post(
            "/api/jobs/db/maintenance",
            json={"keep_latest": 1, "dry_run": False},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["deleted_count"], 0)
        self.assertTrue(managed_dir.exists())
        remaining_ids = [item["job_id"] for item in list_job_records(self.jobs_db_path, limit=None)]
        self.assertEqual(set(remaining_ids), {"job-managed", "job-new"})

    def test_job_db_maintenance_rejects_negative_keep_latest(self) -> None:
        response = self.client.post(
            "/api/jobs/db/maintenance",
            json={"keep_latest": -1},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertIn("keep_latest", payload["error"])


if __name__ == "__main__":
    unittest.main()
