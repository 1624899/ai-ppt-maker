from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import web_app
from ppt_system.jobs.job_store import get_job as get_job_record
from ppt_system.jobs.job_store import init_db as init_job_db
from web_app import app, mutate_job_state, update_job_record


class _FakeExecutor:
    # 用轻量替身拦住后台任务提交，避免操作接口测试触发真实生成链路。
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def submit(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return None


class JobOperationsApiTests(unittest.TestCase):
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
            "default_pages": 2,
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

    def _create_job(self) -> tuple[str, Path]:
        response = self.client.post(
            "/api/jobs",
            data={
                "content": "第一页讲总览，第二页讲拆解。",
                "page_count": "2",
                "image_preset": "landscape_2k",
                "image_quality": "medium",
                "job_target": "editable_ppt",
                "style_notes": "蓝白科技风",
                "include_cover_page": "1",
                "page_richness_default": "medium",
                "page_richness_map": "{}",
                "reference_style_adherence": "balanced",
            },
        )
        self.assertEqual(response.status_code, 202)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        job_id = str(payload["job_id"])
        return job_id, self.output_dir / job_id

    def _seed_completed_pages(self) -> tuple[str, Path]:
        job_id, job_dir = self._create_job()
        refs_dir = job_dir / "01_reference_pages"
        elems_dir = job_dir / "02_elements_pages"
        refs_dir.mkdir(parents=True, exist_ok=True)
        elems_dir.mkdir(parents=True, exist_ok=True)
        for page_no in (1, 2):
            (refs_dir / f"page_{page_no:02d}_reference.png").write_bytes(f"ref-{page_no}".encode("utf-8"))
            (elems_dir / f"page_{page_no:02d}_elements.png").write_bytes(f"elem-{page_no}".encode("utf-8"))

        references = [
            {"page_no": page_no, "title": f"第 {page_no} 页", "image": f"/runs/{job_id}/01_reference_pages/page_{page_no:02d}_reference.png"}
            for page_no in (1, 2)
        ]
        elements = [
            {"page_no": page_no, "image": f"/runs/{job_id}/02_elements_pages/page_{page_no:02d}_elements.png"}
            for page_no in (1, 2)
        ]
        pages = [
            {
                "page_no": page_no,
                "title": f"第 {page_no} 页",
                "summary": f"摘要 {page_no}",
                "status": "completed",
                "reference_image": references[page_no - 1]["image"],
                "element_image": elements[page_no - 1]["image"],
                "reference_prompt": f"参考图提示词 {page_no}",
                "elements_prompt": f"元素图提示词 {page_no}",
            }
            for page_no in (1, 2)
        ]

        mutate_job_state(
            job_dir,
            job_id,
            lambda state: state.update(
                {
                    "status": "completed",
                    "current_stage": "ppt_export",
                    "pages": pages,
                    "reference_pages": references,
                    "element_pages": elements,
                    "result": {
                        "editable_delivery_bundle": {
                            "bundle_path": str(job_dir / "03_ppt_build" / "editable_delivery.bundle.json"),
                            "logical_page_count": 2,
                        }
                    },
                }
            ),
        )
        update_job_record(
            self.jobs_db_path,
            job_id,
            status="completed",
            current_stage="ppt_export",
            stop_requested=False,
        )
        return job_id, job_dir

    def test_agent_instruction_is_recorded_without_submitting_pipeline(self) -> None:
        job_id, _job_dir = self._seed_completed_pages()
        initial_submit_count = len(self.executor.calls)

        response = self.client.post(
            f"/api/jobs/{job_id}/operations",
            json={"operation_type": "agent_instruction", "instruction": "整体改成更商务的蓝白风格"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        self.assertEqual(len(self.executor.calls), initial_submit_count)
        self.assertEqual(payload["operations"][-1]["status"], "accepted")
        self.assertEqual(payload["operations"][-1]["execution"], "pending_backend")

    def test_page_regenerate_backs_up_target_page_and_requeues_pipeline(self) -> None:
        job_id, job_dir = self._seed_completed_pages()
        initial_submit_count = len(self.executor.calls)

        response = self.client.post(
            f"/api/jobs/{job_id}/operations",
            json={"operation_type": "page_regenerate", "page_no": 2, "instruction": "第二页更像流程图"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        self.assertEqual(len(self.executor.calls), initial_submit_count + 1)
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["operations"][-1]["status"], "submitted")

        page_two = next(page for page in payload["pages"] if int(page["page_no"]) == 2)
        self.assertEqual(page_two["reference_image"], "")
        self.assertEqual(page_two["element_image"], "")
        self.assertIn("第二页更像流程图", page_two["reference_prompt"])
        self.assertEqual([item["page_no"] for item in payload["reference_pages"]], [1])
        self.assertEqual([item["page_no"] for item in payload["element_pages"]], [1])

        version = payload["page_versions"][-1]
        self.assertEqual(version["page_no"], 2)
        self.assertTrue(version["artifacts"]["reference"]["exists"])
        self.assertTrue(version["artifacts"]["element"]["exists"])
        self.assertTrue((job_dir / "versions" / "page_02" / version["version_id"] / "reference.png").exists())

    def test_restore_page_version_restores_artifacts_and_requeues_export(self) -> None:
        job_id, _job_dir = self._seed_completed_pages()
        regenerate_response = self.client.post(
            f"/api/jobs/{job_id}/operations",
            json={"operation_type": "page_regenerate", "page_no": 2, "instruction": "第二页更像流程图"},
        )
        self.assertEqual(regenerate_response.status_code, 200)
        regenerate_payload = regenerate_response.get_json()
        self.assertIsNotNone(regenerate_payload)
        version_id = regenerate_payload["page_versions"][-1]["version_id"]

        update_job_record(
            self.jobs_db_path,
            job_id,
            status="completed",
            current_stage="ppt_export",
            stop_requested=False,
        )
        record = get_job_record(self.jobs_db_path, job_id)
        self.assertIsNotNone(record)

        restore_response = self.client.post(
            f"/api/jobs/{job_id}/operations",
            json={"operation_type": "restore_page_version", "page_no": 2, "version_id": version_id},
        )

        self.assertEqual(restore_response.status_code, 200)
        payload = restore_response.get_json()
        self.assertIsNotNone(payload)
        page_two = next(page for page in payload["pages"] if int(page["page_no"]) == 2)
        self.assertIn(f"/runs/{job_id}/versions/page_02/{version_id}/reference.png", page_two["reference_image"])
        self.assertIn(f"/runs/{job_id}/versions/page_02/{version_id}/element.png", page_two["element_image"])
        restored_reference = next(item for item in payload["reference_pages"] if int(item["page_no"]) == 2)
        self.assertEqual(restored_reference["image"], page_two["reference_image"])
        self.assertEqual(payload["status"], "queued")


if __name__ == "__main__":
    unittest.main()
