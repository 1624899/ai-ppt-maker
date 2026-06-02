from __future__ import annotations

import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image

import main
from main import app, load_job_state
from ppt_system.jobs.job_store import get_job as get_job_record
from ppt_system.jobs.job_store import init_db as init_job_db


class _FakeExecutor:
    # 用轻量替身拦截提交，避免接口测试触发真实模型调用。
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def submit(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return None


def _image_file(name: str, *, size: tuple[int, int] = (32, 18), color: str = "#3366CC") -> tuple[io.BytesIO, str]:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    buffer.seek(0)
    return buffer, name


class ExternalReferenceJobApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.temp_root = Path(self.temp_dir.name)
        self.jobs_db_path = self.temp_root / "jobs.sqlite3"
        init_job_db(self.jobs_db_path)

        self.output_dir = self.temp_root / "runs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config = {
            "max_pages": 8,
            "default_pages": 4,
            "default_image_preset": "landscape_small",
            "image_presets": {
                "landscape_small": {
                    "label": "320x180 · 16:9 横图",
                    "width": 320,
                    "height": 180,
                    "size": "320x180",
                    "resolution": "",
                }
            },
            "image_width": 320,
            "image_height": 180,
            "generation_mode": "openai",
            "api_base_url": "https://example.com/v1",
            "image_model": "gpt-image-2",
            "image_size": "320x180",
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
        self.read_config_patch = patch.object(main, "read_config", return_value=self.config)
        self.jobs_db_patch = patch.object(main, "JOBS_DB_PATH", self.jobs_db_path)
        self.executor_patch = patch.object(main, "JOB_EXECUTOR", self.executor)
        self.read_config_patch.start()
        self.jobs_db_patch.start()
        self.executor_patch.start()
        self.addCleanup(self.read_config_patch.stop)
        self.addCleanup(self.jobs_db_patch.stop)
        self.addCleanup(self.executor_patch.stop)
        main.JOB_STATUS_CACHE.clear()

        self.client = app.test_client()

    def test_create_external_reference_job_registers_images_and_submits_resume_pipeline(self) -> None:
        response = self.client.post(
            "/api/jobs",
            data={
                "source_mode": "external_reference",
                "content": "外部设计稿转可编辑 PPT",
                "image_preset": "landscape_small",
                "image_quality": "medium",
                "external_reference_resize_mode": "contain",
                "external_reference_background": "#EEEEEE",
                "reference_images": [
                    _image_file("page_2.png", color="#3366CC"),
                    _image_file("page_10.png", color="#CC6633"),
                ],
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 202)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        job_id = str(payload["job_id"])
        job_dir = self.output_dir / job_id

        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["job_meta"]["source_mode"], "external_reference")
        self.assertEqual(payload["job_meta"]["job_target"], "editable_ppt")
        self.assertEqual(len(payload["reference_pages"]), 2)
        self.assertEqual(payload["pages"][0]["status"], "reference_done")
        self.assertTrue((job_dir / "01_reference_pages" / "page_01_reference.png").exists())
        self.assertTrue((job_dir / "01_reference_pages" / "page_02_reference.png").exists())
        self.assertEqual(len(self.executor.calls), 1)

        record = get_job_record(self.jobs_db_path, job_id)
        self.assertIsNotNone(record)
        self.assertEqual(record["request"]["source_mode"], "external_reference")
        self.assertEqual(record["request"]["external_reference_resize_mode"], "contain")
        self.assertEqual(record["request"]["external_reference_background"], "#EEEEEE")

    def test_create_external_reference_job_can_stop_at_reference_stage(self) -> None:
        response = self.client.post(
            "/api/jobs",
            data={
                "source_mode": "external_reference",
                "image_preset": "landscape_small",
                "image_quality": "medium",
                "external_reference_create_only": "true",
                "reference_images": [_image_file("single.png")],
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 202)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        job_id = str(payload["job_id"])
        job_dir = self.output_dir / job_id

        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["current_stage"], "reference_generation")
        self.assertEqual(payload["job_meta"]["job_target"], "reference_only")
        self.assertEqual(len(self.executor.calls), 0)
        self.assertTrue(any(action["key"] == "reference_ppt" for action in payload["delivery_actions"]))

        saved_state = load_job_state(job_id, job_dir)
        self.assertIsNotNone(saved_state)
        skipped = {stage["key"]: stage["status"] for stage in saved_state["stages"]}
        self.assertEqual(skipped["elements_generation"], "skipped")
        self.assertEqual(skipped["ppt_export"], "skipped")

    def test_external_reference_create_only_job_can_resume_to_editable(self) -> None:
        create_response = self.client.post(
            "/api/jobs",
            data={
                "source_mode": "external_reference",
                "image_preset": "landscape_small",
                "external_reference_create_only": "true",
                "reference_images": [_image_file("resume.png")],
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(create_response.status_code, 202)
        job_id = str(create_response.get_json()["job_id"])

        response = self.client.post(f"/api/jobs/{job_id}/resume")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["job_meta"]["job_target"], "editable_ppt")
        self.assertEqual(len(self.executor.calls), 1)

    def test_external_reference_requires_images(self) -> None:
        response = self.client.post(
            "/api/jobs",
            data={
                "source_mode": "external_reference",
                "image_preset": "landscape_small",
            },
        )

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        self.assertIn("原稿图", payload["error"])


if __name__ == "__main__":
    unittest.main()
