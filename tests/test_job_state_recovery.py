from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import web_app
from ppt_system.jobs.job_store import create_job as create_job_record
from ppt_system.jobs.job_store import get_job as get_job_record
from ppt_system.jobs.job_store import init_db as init_job_db


class JobStateRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.temp_root = Path(self.temp_dir.name)
        self.jobs_db_path = self.temp_root / "jobs.sqlite3"
        init_job_db(self.jobs_db_path)
        self.output_dir = self.temp_root / "runs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config = {"output_dir": str(self.output_dir)}
        self.read_config_patch = patch.object(web_app, "read_config", return_value=self.config)
        self.jobs_db_patch = patch.object(web_app, "JOBS_DB_PATH", self.jobs_db_path)
        self.read_config_patch.start()
        self.jobs_db_patch.start()
        self.addCleanup(self.read_config_patch.stop)
        self.addCleanup(self.jobs_db_patch.stop)
        web_app.JOB_STATUS_CACHE.clear()
        self.client = web_app.app.test_client()

    def test_job_status_request_recovers_orphaned_stopping_job(self) -> None:
        job_id = "orphaned-stopping-job"
        job_dir = self._seed_job(
            job_id=job_id,
            root_status="stopping",
            current_stage="elements_generation",
            stop_requested=True,
            stages=[
                {"key": "planning", "status": "completed", "summary": "", "logs": []},
                {"key": "reference_generation", "status": "completed", "summary": "", "logs": []},
                {"key": "elements_generation", "status": "running", "summary": "正在生成", "logs": []},
            ],
        )

        response = self.client.get(f"/api/jobs/{job_id}")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        self.assertEqual(payload["status"], "interrupted")
        self.assertFalse(payload["stop_requested"])
        active_stage = next(stage for stage in payload["stages"] if stage["key"] == "elements_generation")
        self.assertEqual(active_stage["status"], "interrupted")
        self.assertEqual(active_stage["summary"], "任务已暂停，可继续从当前进度恢复")
        self.assertIn("任务已暂停，可继续从当前进度恢复", active_stage["logs"])

        saved_record = get_job_record(self.jobs_db_path, job_id)
        self.assertIsNotNone(saved_record)
        self.assertEqual(saved_record["status"], "interrupted")
        self.assertFalse(saved_record["stop_requested"])

        saved_state = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(saved_state["status"], "interrupted")
        self.assertFalse(saved_state["stop_requested"])

    def test_delete_job_allows_orphaned_running_task_after_recovery(self) -> None:
        job_id = "orphaned-running-job"
        job_dir = self._seed_job(
            job_id=job_id,
            root_status="running",
            current_stage="planning",
            stop_requested=False,
            stages=[
                {"key": "planning", "status": "running", "summary": "正在规划", "logs": []},
                {"key": "reference_generation", "status": "pending", "summary": "", "logs": []},
            ],
        )

        response = self.client.delete(f"/api/jobs/{job_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True})
        self.assertIsNone(get_job_record(self.jobs_db_path, job_id))
        self.assertFalse(job_dir.exists())

    def test_repair_orphaned_jobs_recovers_running_records_in_bulk(self) -> None:
        job_id = "active-running-job"
        job_dir = self._seed_job(
            job_id=job_id,
            root_status="running",
            current_stage="planning",
            stop_requested=False,
            stages=[
                {"key": "planning", "status": "running", "summary": "正在规划", "logs": []},
                {"key": "reference_generation", "status": "pending", "summary": "", "logs": []},
            ],
        )

        web_app.repair_orphaned_jobs()

        saved_record = get_job_record(self.jobs_db_path, job_id)
        self.assertIsNotNone(saved_record)
        self.assertEqual(saved_record["status"], "interrupted")
        saved_state = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(saved_state["status"], "interrupted")

    def _seed_job(
        self,
        *,
        job_id: str,
        root_status: str,
        current_stage: str,
        stop_requested: bool,
        stages: list[dict[str, object]],
    ) -> Path:
        job_dir = self.output_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        state = {
            "job_id": job_id,
            "status": root_status,
            "current_stage": current_stage,
            "stop_requested": stop_requested,
            "error": "",
            "job_meta": {
                "content": "测试任务",
                "page_count": 2,
                "image_quality": "medium",
                "style_notes": "",
                "job_target": "editable_ppt",
                "job_target_label": "可编辑 PPT",
            },
            "pages": [
                {"page_no": 1, "title": "第 1 页"},
                {"page_no": 2, "title": "第 2 页"},
            ],
            "stages": stages,
            "reference_pages": [],
            "element_pages": [],
            "result": {},
        }
        (job_dir / "status.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        create_job_record(
            self.jobs_db_path,
            {
                "job_id": job_id,
                "status": root_status,
                "current_stage": current_stage,
                "title": "测试任务",
                "content": "测试任务",
                "page_count": 2,
                "image_preset": "landscape_2k",
                "image_quality": "medium",
                "style_notes": "",
                "job_dir": str(job_dir),
                "request": {"content": "测试任务", "page_count": 2, "image_preset": "landscape_2k"},
                "state": state,
                "result": {},
                "stop_requested": stop_requested,
            },
        )
        return job_dir


if __name__ == "__main__":
    unittest.main()
