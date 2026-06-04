from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from ppt_system.jobs.active_job_registry import clear_job_management_registry, mark_job_managed
from ppt_system.jobs.job_store import create_job as create_job_record
from ppt_system.jobs.job_store import init_db as init_job_db
from ppt_system.jobs.job_store import update_job as update_job_record


class JobInterruptApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(clear_job_management_registry)

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
            self.assertEqual(payload["status"], "interrupted")
            self.assertEqual(payload["current_stage"], "reference_generation")
            self.assertFalse(payload["stop_requested"])
            active_payload_stage = next(stage for stage in payload["stages"] if stage["key"] == "reference_generation")
            self.assertEqual(active_payload_stage["status"], "interrupted")
            self.assertEqual(active_payload_stage["summary"], "任务已暂停，可继续从当前进度恢复")
            self.assertIn("任务已暂停，可继续从当前进度恢复", active_payload_stage["logs"])
            self.assertTrue(main.has_job_stop_request(job_dir, job_id))

            updated_state = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(updated_state["status"], "interrupted")
            self.assertEqual(updated_state["current_stage"], "reference_generation")
            self.assertFalse(updated_state["stop_requested"])
            active_stage = next(stage for stage in updated_state["stages"] if stage["key"] == "reference_generation")
            self.assertEqual(active_stage["status"], "interrupted")
            self.assertEqual(active_stage["summary"], "任务已暂停，可继续从当前进度恢复")
            self.assertIn("任务已暂停，可继续从当前进度恢复", active_stage["logs"])

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
            self.assertEqual(payload["status"], "interrupted")
            self.assertEqual(payload["current_stage"], "queued")
            self.assertFalse(payload["stop_requested"])

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

    def test_interrupted_job_keeps_archived_state_when_worker_observes_stop_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            jobs_db_path = base_dir / "jobs.sqlite3"
            init_job_db(jobs_db_path)
            job_id = "job-stop-signal-demo"
            job_dir = base_dir / job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            state = {
                "job_id": job_id,
                "status": "interrupted",
                "current_stage": "ppt_export",
                "error": "",
                "stop_requested": False,
                "stages": [
                    {"key": "ppt_export", "status": "interrupted", "summary": "任务已暂停，可继续从当前进度恢复", "logs": []},
                ],
            }
            (job_dir / "status.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            create_job_record(
                jobs_db_path,
                {
                    "job_id": job_id,
                    "status": "interrupted",
                    "current_stage": "ppt_export",
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

            with patch.object(main, "JOBS_DB_PATH", jobs_db_path):
                main.request_job_stop(job_dir, job_id)
                with self.assertRaises(main.JobInterruptedError):
                    main.ensure_job_not_stopped(job_dir, job_id, "ppt_export")

            updated_state = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(updated_state["status"], "interrupted")
            self.assertFalse(updated_state["stop_requested"])
            active_stage = next(stage for stage in updated_state["stages"] if stage["key"] == "ppt_export")
            self.assertEqual(active_stage["status"], "interrupted")

    def test_resume_waits_while_managed_worker_is_still_stopping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            jobs_db_path = base_dir / "jobs.sqlite3"
            init_job_db(jobs_db_path)
            job_id = "job-managed-stop-signal-demo"
            job_dir = base_dir / job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            state = {
                "job_id": job_id,
                "status": "interrupted",
                "current_stage": "ppt_export",
                "error": "",
                "stop_requested": False,
                "job_meta": {
                    "job_target": "editable_ppt",
                    "generation_options": {},
                },
                "pages": [],
                "reference_pages": [],
                "element_pages": [],
                "result": {},
                "stages": [
                    {"key": "ppt_export", "status": "interrupted", "summary": "任务已暂停，可继续从当前进度恢复", "logs": []},
                ],
            }
            (job_dir / "status.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            create_job_record(
                jobs_db_path,
                {
                    "job_id": job_id,
                    "status": "interrupted",
                    "current_stage": "ppt_export",
                    "title": "测试任务",
                    "content": "测试任务",
                    "page_count": 1,
                    "image_preset": "landscape_2k",
                    "image_quality": "medium",
                    "style_notes": "",
                    "job_dir": str(job_dir),
                    "request": {
                        "content": "测试任务",
                        "page_count": 1,
                        "image_preset": "landscape_2k",
                        "image_quality": "medium",
                        "generation_options": {},
                    },
                    "state": state,
                    "result": {},
                    "stop_requested": False,
                },
            )

            with patch.object(main, "JOBS_DB_PATH", jobs_db_path):
                main.request_job_stop(job_dir, job_id)
                mark_job_managed(job_id)
                client = main.app.test_client()
                response = client.post(f"/api/jobs/{job_id}/resume")

            self.assertEqual(response.status_code, 400)
            payload = response.get_json()
            self.assertIsNotNone(payload)
            self.assertIn("正在停止", payload["error"])

    def test_job_detail_disables_resume_while_managed_worker_is_still_stopping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            jobs_db_path = base_dir / "jobs.sqlite3"
            init_job_db(jobs_db_path)
            job_id = "job-managed-resume-control-demo"
            job_dir = base_dir / job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            state = {
                "job_id": job_id,
                "status": "interrupted",
                "current_stage": "elements_generation",
                "error": "",
                "stop_requested": False,
                "job_meta": {
                    "job_target": "editable_ppt",
                    "generation_options": {},
                },
                "pages": [],
                "reference_pages": [],
                "element_pages": [],
                "result": {},
                "stages": [
                    {"key": "elements_generation", "status": "interrupted", "summary": "任务已暂停，可继续从当前进度恢复", "logs": []},
                ],
            }
            (job_dir / "status.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            create_job_record(
                jobs_db_path,
                {
                    "job_id": job_id,
                    "status": "interrupted",
                    "current_stage": "elements_generation",
                    "title": "测试任务",
                    "content": "测试任务",
                    "page_count": 1,
                    "image_preset": "landscape_2k",
                    "image_quality": "medium",
                    "style_notes": "",
                    "job_dir": str(job_dir),
                    "request": {
                        "content": "测试任务",
                        "page_count": 1,
                        "image_preset": "landscape_2k",
                        "image_quality": "medium",
                        "generation_options": {},
                    },
                    "state": state,
                    "result": {},
                    "stop_requested": False,
                },
            )

            with patch.object(main, "JOBS_DB_PATH", jobs_db_path):
                main.request_job_stop(job_dir, job_id)
                mark_job_managed(job_id)
                main.JOB_STATUS_CACHE.clear()
                client = main.app.test_client()
                response = client.get(f"/api/jobs/{job_id}")

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertIsNotNone(payload)
            resume_control = payload["resume_control"]
            self.assertFalse(resume_control["can_resume"])
            self.assertTrue(resume_control["is_waiting_for_stop"])
            self.assertEqual(resume_control["label"], "停止收尾中")

    def test_stale_stopping_job_is_archived_on_status_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            jobs_db_path = base_dir / "jobs.sqlite3"
            init_job_db(jobs_db_path)
            job_id = "job-stale-stopping-demo"
            job_dir = base_dir / job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            state = {
                "job_id": job_id,
                "status": "stopping",
                "current_stage": "ppt_export",
                "error": "",
                "stop_requested": True,
                "stages": [
                    {"key": "planning", "status": "completed", "summary": "", "logs": []},
                    {"key": "ppt_export", "status": "stopping", "summary": "暂停请求已发送，正在等待当前步骤收尾", "logs": []},
                ],
            }
            (job_dir / "status.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            create_job_record(
                jobs_db_path,
                {
                    "job_id": job_id,
                    "status": "stopping",
                    "current_stage": "ppt_export",
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
            update_job_record(jobs_db_path, job_id, touch_updated_at=False, updated_at="2026-01-01 00:00:01.000")

            with patch.object(main, "JOBS_DB_PATH", jobs_db_path), patch.object(
                main,
                "read_config",
                return_value={"output_dir": str(base_dir), "stopping_grace_seconds": 1},
            ):
                main.JOB_STATUS_CACHE.clear()
                client = main.app.test_client()
                response = client.get(f"/api/jobs/{job_id}")

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual(payload["status"], "interrupted")
            self.assertFalse(payload["stop_requested"])
            active_stage = next(stage for stage in payload["stages"] if stage["key"] == "ppt_export")
            self.assertEqual(active_stage["status"], "interrupted")
            self.assertEqual(active_stage["summary"], "任务已暂停，可继续从当前进度恢复")

            updated_record = main.get_job_record(jobs_db_path, job_id)
            self.assertIsNotNone(updated_record)
            self.assertEqual(updated_record["status"], "interrupted")
            self.assertFalse(updated_record["stop_requested"])
            updated_state = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(updated_state["status"], "interrupted")
            self.assertFalse(updated_state["stop_requested"])

    def test_managed_stopping_job_is_not_archived_as_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            jobs_db_path = base_dir / "jobs.sqlite3"
            init_job_db(jobs_db_path)
            job_id = "job-managed-stopping-demo"
            job_dir = base_dir / job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            state = {
                "job_id": job_id,
                "status": "stopping",
                "current_stage": "ppt_export",
                "error": "",
                "stop_requested": True,
                "stages": [
                    {"key": "ppt_export", "status": "stopping", "summary": "暂停请求已发送，正在等待当前步骤收尾", "logs": []},
                ],
            }
            (job_dir / "status.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            create_job_record(
                jobs_db_path,
                {
                    "job_id": job_id,
                    "status": "stopping",
                    "current_stage": "ppt_export",
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
            update_job_record(jobs_db_path, job_id, touch_updated_at=False, updated_at="2026-01-01 00:00:01.000")
            mark_job_managed(job_id)

            with patch.object(main, "JOBS_DB_PATH", jobs_db_path), patch.object(
                main,
                "read_config",
                return_value={"output_dir": str(base_dir), "stopping_grace_seconds": 1},
            ):
                main.JOB_STATUS_CACHE.clear()
                client = main.app.test_client()
                response = client.get(f"/api/jobs/{job_id}")

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual(payload["status"], "stopping")
            self.assertTrue(payload["stop_requested"])


if __name__ == "__main__":
    unittest.main()
