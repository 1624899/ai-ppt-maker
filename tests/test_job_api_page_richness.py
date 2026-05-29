from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ppt_system.job_store import get_job as get_job_record
from ppt_system.job_store import init_db as init_job_db
from web_app import app, load_job_state, mutate_job_state, status_file, update_job_record
import web_app


class _FakeExecutor:
    # 用轻量替身拦住后台任务提交，避免接口测试意外触发真实生成链路。
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def submit(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return None


class JobApiPageRichnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.temp_root = Path(self.temp_dir.name)
        self.jobs_db_path = self.temp_root / "jobs.sqlite3"
        init_job_db(self.jobs_db_path)

        self.output_dir = self.temp_root / "runs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config = {
            "max_pages": 10,
            "default_pages": 4,
            "default_image_preset": "landscape_2k",
            "image_presets": {
                "landscape_2k": {
                    "label": "2048x1152 · 16:9 2K 横图",
                    "width": 2048,
                    "height": 1152,
                    "size": "2048x1152",
                    "resolution": "",
                }
            },
            "image_width": 2048,
            "image_height": 1152,
            "generation_mode": "openai",
            "api_base_url": "https://example.com/v1",
            "image_model": "gpt-image-2",
            "image_size": "2048x1152",
            "image_resolution": "",
            "image_quality": "medium",
            "image_background": "opaque",
            "image_output_format": "png",
            "output_dir": str(self.output_dir),
            "model_configs": {"chat": [], "image": []},
            "active_chat_config_id": "",
            "active_image_config_id": "",
        }

        self.executor = _FakeExecutor()
        self.read_config_patch = patch.object(web_app, "read_config", return_value=self.config)
        self.jobs_db_patch = patch.object(web_app, "JOBS_DB_PATH", self.jobs_db_path)
        self.executor_patch = patch.object(web_app, "JOB_EXECUTOR", self.executor)
        self.read_config_patch.start()
        self.jobs_db_patch.start()
        self.executor_patch.start()
        self.addCleanup(self.read_config_patch.stop)
        self.addCleanup(self.jobs_db_patch.stop)
        self.addCleanup(self.executor_patch.stop)
        web_app.JOB_STATUS_CACHE.clear()

        self.client = app.test_client()

    def test_create_job_persists_page_richness_generation_options(self) -> None:
        response = self.client.post(
            "/api/jobs",
            data={
                "content": "第一页讲总览，第二页讲拆解。",
                "page_count": "2",
                "image_preset": "landscape_2k",
                "image_quality": "medium",
                "job_target": "reference_only",
                "style_notes": "蓝白科技风",
                "include_cover_page": "1",
                "page_richness_default": "high",
                "page_richness_map": '{"1":"low","2":"medium"}',
            },
        )

        self.assertEqual(response.status_code, 202)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        job_id = str(payload["job_id"])
        self.assertEqual(payload["job_meta"]["generation_options"]["page_richness_default"], "high")
        self.assertEqual(
            payload["job_meta"]["generation_options"]["page_richness_map"],
            {"1": "low", "2": "medium"},
        )

        record = get_job_record(self.jobs_db_path, job_id)
        self.assertIsNotNone(record)
        self.assertEqual(record["request"]["generation_options"]["page_richness_default"], "high")
        self.assertEqual(
            record["request"]["generation_options"]["page_richness_map"],
            {"1": "low", "2": "medium"},
        )
        self.assertEqual(record["request"]["job_target"], "reference_only")
        self.assertEqual(payload["job_meta"]["job_target"], "reference_only")
        self.assertEqual(len(self.executor.calls), 1)

    def test_resume_job_reuses_saved_page_richness_generation_options(self) -> None:
        create_response = self.client.post(
            "/api/jobs",
            data={
                "content": "第一页讲总览，第二页讲拆解。",
                "page_count": "2",
                "image_preset": "landscape_2k",
                "image_quality": "medium",
                "style_notes": "蓝白科技风",
                "include_cover_page": "0",
                "page_richness_default": "medium",
                "page_richness_map": '{"1":"high","2":"low"}',
            },
        )
        self.assertEqual(create_response.status_code, 202)
        payload = create_response.get_json()
        self.assertIsNotNone(payload)
        job_id = str(payload["job_id"])
        job_dir = self.output_dir / job_id

        update_job_record(
            self.jobs_db_path,
            job_id,
            status="interrupted",
            current_stage="planning",
            stop_requested=False,
        )
        mutate_job_state(
            job_dir,
            job_id,
            lambda state: state.update(
                {
                    "status": "interrupted",
                    "current_stage": "planning",
                    "error": "",
                    "stop_requested": False,
                }
            ),
        )

        response = self.client.post(f"/api/jobs/{job_id}/resume")
        self.assertEqual(response.status_code, 200)
        resumed = response.get_json()
        self.assertIsNotNone(resumed)
        self.assertEqual(resumed["job_meta"]["generation_options"]["page_richness_default"], "medium")
        self.assertEqual(
            resumed["job_meta"]["generation_options"]["page_richness_map"],
            {"1": "high", "2": "low"},
        )

        saved_state = load_job_state(job_id, job_dir)
        self.assertIsNotNone(saved_state)
        self.assertEqual(saved_state["status"], "queued")
        self.assertEqual(saved_state["job_meta"]["generation_options"]["page_richness_default"], "medium")
        self.assertEqual(
            saved_state["job_meta"]["generation_options"]["page_richness_map"],
            {"1": "high", "2": "low"},
        )
        self.assertTrue(status_file(job_dir).exists())
        self.assertEqual(len(self.executor.calls), 2)

    def test_resume_completed_reference_only_job_upgrades_target_to_editable(self) -> None:
        create_response = self.client.post(
            "/api/jobs",
            data={
                "content": "第一页讲总览，第二页讲拆解。",
                "page_count": "2",
                "image_preset": "landscape_2k",
                "image_quality": "medium",
                "job_target": "reference_only",
                "style_notes": "蓝白科技风",
                "include_cover_page": "1",
                "page_richness_default": "medium",
                "page_richness_map": '{"1":"medium","2":"high"}',
            },
        )
        self.assertEqual(create_response.status_code, 202)
        payload = create_response.get_json()
        self.assertIsNotNone(payload)
        job_id = str(payload["job_id"])
        job_dir = self.output_dir / job_id

        update_job_record(
            self.jobs_db_path,
            job_id,
            status="completed",
            current_stage="reference_generation",
            request={**get_job_record(self.jobs_db_path, job_id)["request"], "job_target": "reference_only"},
            stop_requested=False,
        )
        mutate_job_state(
            job_dir,
            job_id,
            lambda state: state.update(
                {
                    "status": "completed",
                    "current_stage": "reference_generation",
                    "error": "",
                    "stop_requested": False,
                    "job_meta": {
                        **state.get("job_meta", {}),
                        "job_target": "reference_only",
                        "job_target_label": "图片版 PPT",
                    },
                }
            ),
        )

        response = self.client.post(f"/api/jobs/{job_id}/resume")
        self.assertEqual(response.status_code, 200)
        resumed = response.get_json()
        self.assertIsNotNone(resumed)
        self.assertEqual(resumed["job_meta"]["job_target"], "editable_ppt")

        saved_record = get_job_record(self.jobs_db_path, job_id)
        self.assertIsNotNone(saved_record)
        self.assertEqual(saved_record["request"]["job_target"], "editable_ppt")
        self.assertEqual(len(self.executor.calls), 2)


if __name__ == "__main__":
    unittest.main()
