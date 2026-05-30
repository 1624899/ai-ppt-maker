from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from ppt_system.jobs.job_store import create_job as create_job_record
from ppt_system.jobs.job_store import init_db as init_job_db


class JobInterruptApiTests(unittest.TestCase):
    def _create_interruptible_job(
        self,
        *,
        base_dir: Path,
        jobs_db_path: Path,
        job_id: str,
        status: str,
        current_stage: str,
    ) -> Path:
        job_dir = base_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        state = {
            "job_id": job_id,
            "status": status,
            "current_stage": current_stage,
            "stop_requested": False,
            "stages": [
                {"key": "planning", "status": "completed", "summary": "", "logs": []},
                {"key": "reference_generation", "status": "running", "summary": "", "logs": []},
                {"key": "elements_generation", "status": "pending", "summary": "", "logs": []},
            ],
        }
        (job_dir / "status.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

        create_job_record(
            jobs_db_path,
            {
                "job_id": job_id,
                "status": status,
                "current_stage": current_stage,
                "title": "测试任务",
                "content": "测试任务",
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
        return job_dir

    def test_interrupt_returns_updated_state_for_immediate_ui_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            jobs_db_path = base_dir / "jobs.sqlite3"
            init_job_db(jobs_db_path)
            job_id = "job-interrupt-demo"
            job_dir = self._create_interruptible_job(
                base_dir=base_dir,
                jobs_db_path=jobs_db_path,
                job_id=job_id,
                status="running",
                current_stage="reference_generation",
            )

            with patch.object(main, "JOBS_DB_PATH", jobs_db_path):
                client = main.app.test_client()
                response = client.post(f"/api/jobs/{job_id}/interrupt")

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertIsNotNone(payload)
            self.assertEqual(payload["job_id"], job_id)
            self.assertEqual(payload["status"], "stopping")
            self.assertEqual(payload["current_stage"], "reference_generation")
            self.assertTrue(payload["stop_requested"])
            active_payload_stage = next(stage for stage in payload["stages"] if stage["key"] == "reference_generation")
            self.assertEqual(active_payload_stage["status"], "stopping")
            self.assertEqual(active_payload_stage["summary"], "暂停请求已发送，正在等待当前步骤收尾")
            self.assertIn("暂停请求已发送，正在等待当前步骤收尾", active_payload_stage["logs"])

            updated_state = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(updated_state["status"], "stopping")
            self.assertEqual(updated_state["current_stage"], "reference_generation")
            self.assertTrue(updated_state["stop_requested"])
            active_stage = next(stage for stage in updated_state["stages"] if stage["key"] == "reference_generation")
            self.assertEqual(active_stage["status"], "stopping")
            self.assertEqual(active_stage["summary"], "暂停请求已发送，正在等待当前步骤收尾")
            self.assertIn("暂停请求已发送，正在等待当前步骤收尾", active_stage["logs"])

    def test_interrupt_returns_state_for_queued_job_without_active_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            jobs_db_path = base_dir / "jobs.sqlite3"
            init_job_db(jobs_db_path)
            job_id = "job-interrupt-queued-demo"
            self._create_interruptible_job(
                base_dir=base_dir,
                jobs_db_path=jobs_db_path,
                job_id=job_id,
                status="queued",
                current_stage="queued",
            )

            with patch.object(main, "JOBS_DB_PATH", jobs_db_path):
                client = main.app.test_client()
                response = client.post(f"/api/jobs/{job_id}/interrupt")

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertIsNotNone(payload)
            self.assertEqual(payload["job_id"], job_id)
            self.assertEqual(payload["status"], "stopping")
            self.assertEqual(payload["current_stage"], "queued")
            self.assertTrue(payload["stop_requested"])

    def test_stopped_queued_job_is_interrupted_when_worker_starts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            jobs_db_path = base_dir / "jobs.sqlite3"
            init_job_db(jobs_db_path)
            job_id = "job-queued-stop-demo"
            job_dir = base_dir / job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            state = {
                "job_id": job_id,
                "status": "stopping",
                "current_stage": "queued",
                "error": "",
                "stop_requested": True,
                "job_meta": {"job_target": "editable_ppt"},
                "pages": [],
                "reference_pages": [],
                "element_pages": [],
                "result": {},
                "stages": [
                    {"key": "planning", "status": "pending", "summary": "", "logs": []},
                    {"key": "reference_generation", "status": "pending", "summary": "", "logs": []},
                    {"key": "elements_generation", "status": "pending", "summary": "", "logs": []},
                    {"key": "ppt_export", "status": "pending", "summary": "", "logs": []},
                ],
            }
            (job_dir / "status.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            create_job_record(
                jobs_db_path,
                {
                    "job_id": job_id,
                    "status": "stopping",
                    "current_stage": "queued",
                    "title": "测试任务",
                    "content": "测试任务",
                    "page_count": 1,
                    "image_preset": "landscape_2k",
                    "image_quality": "medium",
                    "style_notes": "",
                    "job_dir": str(job_dir),
                    "request": {},
                    "state": state,
                    "result": {},
                    "stop_requested": True,
                },
            )

            with patch.object(main, "JOBS_DB_PATH", jobs_db_path):
                main.JOB_STATUS_CACHE.clear()
                main.run_job_pipeline(
                    job_id,
                    job_dir,
                    {},
                    {},
                    "",
                    1,
                    {},
                    "",
                    {},
                    job_dir / "01_reference_pages",
                    job_dir / "02_elements_pages",
                    job_dir / "style_refs",
                )

            updated_state = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(updated_state["status"], "interrupted")
            self.assertEqual(updated_state["current_stage"], "queued")
            self.assertFalse(updated_state["stop_requested"])
            updated_record = main.get_job_record(jobs_db_path, job_id)
            self.assertIsNotNone(updated_record)
            self.assertEqual(updated_record["status"], "interrupted")
            self.assertFalse(updated_record["stop_requested"])


if __name__ == "__main__":
    unittest.main()
