from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import web_app


class JobInterruptApiTests(unittest.TestCase):
    def test_interrupt_marks_job_interrupted_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            job_id = "job-interrupt-demo"
            job_dir = base_dir / job_id
            job_dir.mkdir(parents=True, exist_ok=True)

            state = {
                "job_id": job_id,
                "status": "running",
                "current_stage": "reference_generation",
                "stop_requested": False,
                "stages": [
                    {"key": "planning", "status": "completed", "summary": "", "logs": []},
                    {"key": "reference_generation", "status": "running", "summary": "", "logs": []},
                    {"key": "elements_generation", "status": "pending", "summary": "", "logs": []},
                ],
            }
            (job_dir / "status.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

            record = {
                "job_id": job_id,
                "status": "running",
                "current_stage": "reference_generation",
                "stop_requested": False,
                "job_dir": str(job_dir),
            }

            with patch.object(web_app, "JOBS_DB_PATH", base_dir / "jobs.sqlite3"), patch.object(
                web_app, "get_job_record", return_value=record
            ):
                client = web_app.app.test_client()
                response = client.post(f"/api/jobs/{job_id}/interrupt")

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual(payload, {"ok": True})

            updated_state = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(updated_state["status"], "interrupted")
            self.assertEqual(updated_state["current_stage"], "reference_generation")
            self.assertTrue(updated_state["stop_requested"])
            active_stage = next(stage for stage in updated_state["stages"] if stage["key"] == "reference_generation")
            self.assertEqual(active_stage["status"], "interrupted")
            self.assertEqual(active_stage["summary"], "任务已暂停")
            self.assertIn("任务已暂停", active_stage["logs"])


if __name__ == "__main__":
    unittest.main()
