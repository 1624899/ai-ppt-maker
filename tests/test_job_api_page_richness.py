from __future__ import annotations

import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ppt_system.jobs.job_store import get_job as get_job_record
from ppt_system.jobs.job_store import init_db as init_job_db
from ppt_system.export.export_layer_mode import OVERLAY_LAYER_MODE, SEPARATE_LAYER_MODE
from main import app, load_job_state, mutate_job_state, status_file, update_job_record
import main


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

    def _seed_completed_reference_job(self, *, job_target: str = "reference_only") -> tuple[str, Path]:
        create_response = self.client.post(
            "/api/jobs",
            data={
                "content": "第一页讲总览，第二页讲拆解。",
                "page_count": "2",
                "image_preset": "landscape_2k",
                "image_quality": "medium",
                "job_target": job_target,
                "style_notes": "蓝白科技风",
                "include_cover_page": "1",
                "page_richness_default": "medium",
                "page_richness_map": '{"1":"medium","2":"high"}',
                "reference_style_adherence": "balanced",
            },
        )
        self.assertEqual(create_response.status_code, 202)
        payload = create_response.get_json()
        self.assertIsNotNone(payload)
        job_id = str(payload["job_id"])
        job_dir = self.output_dir / job_id
        (job_dir / "01_reference_pages").mkdir(parents=True, exist_ok=True)
        for page_no in (1, 2):
            (job_dir / "01_reference_pages" / f"page_{page_no:02d}_reference.png").write_bytes(b"fake")
        return job_id, job_dir

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
                "reference_style_adherence": "strict",
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
        self.assertEqual(payload["job_meta"]["generation_options"]["reference_style_adherence"], "strict")

        record = get_job_record(self.jobs_db_path, job_id)
        self.assertIsNotNone(record)
        self.assertEqual(record["request"]["generation_options"]["page_richness_default"], "high")
        self.assertEqual(
            record["request"]["generation_options"]["page_richness_map"],
            {"1": "low", "2": "medium"},
        )
        self.assertEqual(record["request"]["generation_options"]["reference_style_adherence"], "strict")
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
                "reference_style_adherence": "loose",
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
        self.assertEqual(resumed["job_meta"]["generation_options"]["reference_style_adherence"], "loose")

        saved_state = load_job_state(job_id, job_dir)
        self.assertIsNotNone(saved_state)
        self.assertEqual(saved_state["status"], "queued")
        self.assertEqual(saved_state["job_meta"]["generation_options"]["page_richness_default"], "medium")
        self.assertEqual(
            saved_state["job_meta"]["generation_options"]["page_richness_map"],
            {"1": "high", "2": "low"},
        )
        self.assertEqual(saved_state["job_meta"]["generation_options"]["reference_style_adherence"], "loose")
        self.assertTrue(status_file(job_dir).exists())
        self.assertEqual(len(self.executor.calls), 2)

    def test_resume_reconciles_unmanaged_terminal_stage_record(self) -> None:
        create_response = self.client.post(
            "/api/jobs",
            data={
                "content": "第一页讲总览。",
                "page_count": "1",
                "image_preset": "landscape_2k",
                "image_quality": "medium",
                "style_notes": "蓝白科技风",
            },
        )
        self.assertEqual(create_response.status_code, 202)
        payload = create_response.get_json()
        self.assertIsNotNone(payload)
        job_id = str(payload["job_id"])
        job_dir = self.output_dir / job_id

        def mark_stage_interrupted(state: dict[str, object]) -> None:
            state["status"] = "running"
            state["current_stage"] = "ppt_export"
            state["stop_requested"] = False
            for stage in state.get("stages", []):
                if isinstance(stage, dict) and stage.get("key") == "ppt_export":
                    stage["status"] = "interrupted"
                    stage["summary"] = "任务已暂停，可继续从当前进度恢复"

        mutate_job_state(job_dir, job_id, mark_stage_interrupted)
        update_job_record(
            self.jobs_db_path,
            job_id,
            status="running",
            current_stage="ppt_export",
            stop_requested=False,
        )
        main.JOB_STATUS_CACHE.clear()

        response = self.client.post(f"/api/jobs/{job_id}/resume")

        self.assertEqual(response.status_code, 200)
        saved_state = load_job_state(job_id, job_dir)
        self.assertIsNotNone(saved_state)
        self.assertEqual(saved_state["status"], "queued")
        resumed_stage = next(stage for stage in saved_state["stages"] if stage["key"] == "ppt_export")
        self.assertEqual(resumed_stage["status"], "pending")
        self.assertEqual(resumed_stage["summary"], "等待继续执行")
        saved_record = get_job_record(self.jobs_db_path, job_id)
        self.assertIsNotNone(saved_record)
        self.assertEqual(saved_record["status"], "queued")
        self.assertEqual(len(self.executor.calls), 2)

    def test_resume_completed_reference_only_job_upgrades_target_to_editable(self) -> None:
        job_id, job_dir = self._seed_completed_reference_job(job_target="reference_only")

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

    def test_deliver_reference_ppt_updates_result_payload(self) -> None:
        job_id, job_dir = self._seed_completed_reference_job(job_target="reference_only")
        references = [
            {"page_no": 1, "image": f"/runs/{job_id}/01_reference_pages/page_01_reference.png"},
            {"page_no": 2, "image": f"/runs/{job_id}/01_reference_pages/page_02_reference.png"},
        ]

        update_job_record(
            self.jobs_db_path,
            job_id,
            status="completed",
            current_stage="reference_generation",
            stop_requested=False,
        )
        mutate_job_state(
            job_dir,
            job_id,
            lambda state: state.update(
                {
                    "status": "completed",
                    "current_stage": "reference_generation",
                    "reference_pages": references,
                    "pages": [
                        {
                            "page_no": 1,
                            "reference_image": references[0]["image"],
                            "element_image": "",
                        },
                        {
                            "page_no": 2,
                            "reference_image": references[1]["image"],
                            "element_image": "",
                        },
                    ],
                    "result": {},
                }
            ),
        )

        def fake_reference_export(reference_pages, job_dir_value, output_pptx, *, image_width, image_height):
            output_pptx.write_bytes(b"reference pptx")
            return {"page_count": 2}

        with patch.object(main, "export_reference_images_to_pptx", side_effect=fake_reference_export):
            response = self.client.post(
                f"/api/jobs/{job_id}/deliver",
                json={"delivery_key": "reference_ppt"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        reference_action = next(item for item in payload["delivery_actions"] if item["key"] == "reference_ppt")
        self.assertTrue(reference_action["generated"])
        self.assertEqual(reference_action["generated_file"]["page_count"], 2)

        record = get_job_record(self.jobs_db_path, job_id)
        self.assertIsNotNone(record)
        deliveries = record["state"]["result"]["deliveries"]
        self.assertIn("reference_ppt", deliveries)
        self.assertEqual(deliveries["reference_ppt"]["delivery_mode"], "reference_only")

    def test_deliver_editable_ppt_supports_overlay_and_separate_modes(self) -> None:
        job_id, job_dir = self._seed_completed_reference_job(job_target="editable_ppt")
        bundle_dir = job_dir / "03_ppt_build"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        bundle_path = bundle_dir / "editable_delivery.bundle.json"
        bundle_path.write_text(
            json.dumps(
                {
                    "bundle_path": str(bundle_path),
                    "logical_page_count": 2,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        references = [
            {"page_no": 1, "image": f"/runs/{job_id}/01_reference_pages/page_01_reference.png"},
            {"page_no": 2, "image": f"/runs/{job_id}/01_reference_pages/page_02_reference.png"},
        ]
        elements = [
            {"page_no": 1, "image": f"/runs/{job_id}/02_elements_pages/page_01_elements.png"},
            {"page_no": 2, "image": f"/runs/{job_id}/02_elements_pages/page_02_elements.png"},
        ]
        (job_dir / "02_elements_pages").mkdir(parents=True, exist_ok=True)
        for page_no in (1, 2):
            (job_dir / "02_elements_pages" / f"page_{page_no:02d}_elements.png").write_bytes(b"fake")

        mutate_job_state(
            job_dir,
            job_id,
            lambda state: state.update(
                {
                    "status": "completed",
                    "current_stage": "ppt_export",
                    "reference_pages": references,
                    "element_pages": elements,
                    "result": {
                        "editable_delivery_bundle": {
                            "bundle_path": str(bundle_path),
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

        def fake_export(bundle_path_value, output_pptx, *, layer_mode):
            output_pptx.write_bytes(f"editable-{layer_mode}".encode("utf-8"))
            return {
                "output_pptx": str(output_pptx),
                "page_count": 4 if layer_mode == SEPARATE_LAYER_MODE else 2,
                "logical_page_count": 2,
                "delivery_mode": "separate_layer_slides" if layer_mode == SEPARATE_LAYER_MODE else "overlay_slides",
                "layer_mode": layer_mode,
                "label": "双页" if layer_mode == SEPARATE_LAYER_MODE else "合页",
                "description": "desc",
            }

        with patch.object(main, "export_editable_delivery", side_effect=fake_export):
            separate_response = self.client.post(
                f"/api/jobs/{job_id}/deliver",
                json={"delivery_key": "editable_ppt_separate"},
            )
            overlay_response = self.client.post(
                f"/api/jobs/{job_id}/deliver",
                json={"delivery_key": "editable_ppt_overlay"},
            )

        self.assertEqual(separate_response.status_code, 200)
        self.assertEqual(overlay_response.status_code, 200)
        overlay_payload = overlay_response.get_json()
        self.assertIsNotNone(overlay_payload)
        actions_by_key = {item["key"]: item for item in overlay_payload["delivery_actions"]}
        self.assertEqual(
            [
                item["key"]
                for item in overlay_payload["delivery_actions"]
                if item.get("delivery_key") == "editable_ppt"
            ],
            ["editable_ppt_overlay", "editable_ppt_separate"],
        )
        self.assertEqual(actions_by_key["editable_ppt_overlay"]["label"], "可编辑ppt单页生成")
        self.assertEqual(actions_by_key["editable_ppt_overlay"]["delivery_key"], "editable_ppt")
        self.assertEqual(actions_by_key["editable_ppt_overlay"]["layer_mode"], OVERLAY_LAYER_MODE)
        self.assertTrue(actions_by_key["editable_ppt_overlay"]["generated"])
        self.assertEqual(actions_by_key["editable_ppt_overlay"]["generated_file"]["layer_mode"], OVERLAY_LAYER_MODE)
        self.assertEqual(actions_by_key["editable_ppt_separate"]["label"], "文字/元素拆分双页生成")
        self.assertEqual(actions_by_key["editable_ppt_separate"]["delivery_key"], "editable_ppt")
        self.assertEqual(actions_by_key["editable_ppt_separate"]["layer_mode"], SEPARATE_LAYER_MODE)
        self.assertTrue(actions_by_key["editable_ppt_separate"]["generated"])
        self.assertEqual(actions_by_key["editable_ppt_separate"]["generated_file"]["layer_mode"], SEPARATE_LAYER_MODE)

        record = get_job_record(self.jobs_db_path, job_id)
        self.assertIsNotNone(record)
        by_layer_mode = record["state"]["result"]["deliveries"]["editable_ppt"]["by_layer_mode"]
        self.assertIn(SEPARATE_LAYER_MODE, by_layer_mode)
        self.assertIn(OVERLAY_LAYER_MODE, by_layer_mode)

    def test_deliver_editable_ppt_reuses_fresh_existing_overlay_file(self) -> None:
        job_id, job_dir = self._seed_completed_reference_job(job_target="editable_ppt")
        bundle_dir = job_dir / "03_ppt_build"
        work_dir = bundle_dir
        bundle_dir.mkdir(parents=True, exist_ok=True)
        bundle_path = bundle_dir / "editable_delivery.bundle.json"
        output_pptx = job_dir / "result.editable.overlay.pptx"
        bundle_path.write_text(
            json.dumps(
                {
                    "project": {"pages": [{"page_no": 1}, {"page_no": 2}]},
                    "work_dir": str(work_dir),
                    "assets": {},
                    "page_results": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        output_pptx.write_bytes(b"existing pptx")
        bundle_mtime = bundle_path.stat().st_mtime
        output_mtime = max(output_pptx.stat().st_mtime, bundle_mtime + 1)
        import os

        os.utime(output_pptx, (output_mtime, output_mtime))

        mutate_job_state(
            job_dir,
            job_id,
            lambda state: state.update(
                {
                    "status": "completed",
                    "current_stage": "ppt_export",
                    "result": {
                        "editable_delivery_bundle": {
                            "bundle_path": str(bundle_path),
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

        with patch.object(main, "export_editable_delivery", side_effect=AssertionError("不应重新导出")):
            response = self.client.post(
                f"/api/jobs/{job_id}/deliver",
                json={"delivery_key": "editable_ppt_overlay"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        actions_by_key = {item["key"]: item for item in payload["delivery_actions"]}
        generated_file = actions_by_key["editable_ppt_overlay"]["generated_file"]
        self.assertEqual(generated_file["pptx_path"], str(output_pptx))
        self.assertEqual(generated_file["logical_page_count"], 2)
        self.assertEqual(generated_file["page_count"], 2)


if __name__ == "__main__":
    unittest.main()
