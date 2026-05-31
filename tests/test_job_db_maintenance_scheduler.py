from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from ppt_system.jobs.db_maintenance_scheduler import JobDbMaintenanceScheduler
from ppt_system.jobs.db_maintenance_scheduler import resolve_job_db_maintenance_config


class JobDbMaintenanceSchedulerTests(unittest.TestCase):
    def test_resolve_job_db_maintenance_config_applies_defaults_and_bounds(self) -> None:
        resolved = resolve_job_db_maintenance_config(
            {
                "job_db_maintenance_enabled": True,
                "job_db_maintenance_interval_seconds": 5,
                "job_db_maintenance_keep_latest": -3,
                "job_db_maintenance_include_pinned": True,
                "job_db_maintenance_vacuum": False,
                "job_db_maintenance_min_reclaimable_bytes": -1,
            }
        )

        self.assertTrue(resolved["enabled"])
        self.assertEqual(resolved["interval_seconds"], 60)
        self.assertEqual(resolved["keep_latest"], 0)
        self.assertTrue(resolved["include_pinned"])
        self.assertFalse(resolved["vacuum"])
        self.assertEqual(resolved["min_reclaimable_bytes"], 0)

    def test_scheduler_runs_maintenance_when_cleanup_needed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "jobs.sqlite3"
            calls: list[dict[str, object]] = []
            completed = threading.Event()

            def config_loader() -> dict[str, object]:
                return {
                    "job_db_maintenance_enabled": True,
                    "job_db_maintenance_interval_seconds": 60,
                    "job_db_maintenance_keep_latest": 20,
                    "job_db_maintenance_include_pinned": False,
                    "job_db_maintenance_vacuum": True,
                    "job_db_maintenance_min_reclaimable_bytes": 1024,
                }

            def stats_collector(_db_path: Path) -> dict[str, int]:
                return {
                    "job_count": 25,
                    "reclaimable_bytes": 2048,
                }

            def maintenance_runner(target_db_path: Path, **kwargs: object) -> dict[str, object]:
                calls.append({"db_path": str(target_db_path), **kwargs})
                completed.set()
                return {"deleted_count": 2}

            scheduler = JobDbMaintenanceScheduler(
                db_path=db_path,
                config_loader=config_loader,
                maintenance_runner=maintenance_runner,
                stats_collector=stats_collector,
                running_jobs_counter=lambda: 0,
                sleep_interval_seconds=0.05,
            )
            try:
                scheduler.start()
                scheduler.trigger_now()
                self.assertTrue(completed.wait(1.5))
                snapshot = scheduler.snapshot()
            finally:
                scheduler.stop()

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["keep_latest"], 20)
        self.assertEqual(calls[0]["dry_run"], False)
        self.assertEqual(calls[0]["vacuum"], True)
        self.assertTrue(snapshot["running"])
        self.assertEqual(snapshot["last_result"]["status"], "completed")

    def test_scheduler_skips_when_running_jobs_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "jobs.sqlite3"
            calls: list[dict[str, object]] = []

            scheduler = JobDbMaintenanceScheduler(
                db_path=db_path,
                config_loader=lambda: {"job_db_maintenance_enabled": True},
                maintenance_runner=lambda target_db_path, **kwargs: calls.append({"db_path": str(target_db_path), **kwargs}) or {},
                stats_collector=lambda _db_path: {"job_count": 100, "reclaimable_bytes": 1024 * 1024 * 64},
                running_jobs_counter=lambda: 2,
                sleep_interval_seconds=0.05,
            )
            try:
                scheduler.start()
                scheduler.trigger_now()
                deadline = time.time() + 1.5
                snapshot = scheduler.snapshot()
                while time.time() < deadline:
                    snapshot = scheduler.snapshot()
                    last_result = snapshot.get("last_result") or {}
                    if last_result.get("status") == "skipped":
                        break
                    time.sleep(0.05)
                self.assertEqual((snapshot.get("last_result") or {}).get("status"), "skipped")
            finally:
                scheduler.stop()

        self.assertEqual(calls, [])
        self.assertEqual(snapshot["last_result"]["reason"], "running_jobs")


if __name__ == "__main__":
    unittest.main()
