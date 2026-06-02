from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import main
from main import app, load_job_state, mutate_job_state, update_job_record
from ppt_system.jobs.job_store import get_job as get_job_record
from ppt_system.jobs.job_store import init_db as init_job_db


class _FakeExecutor:
    # 用轻量替身拦截提交，避免接口测试触发真实模型调用。
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def submit(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return None


class GuidedWorkflowApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.temp_root = Path(self.temp_dir.name)
        self.jobs_db_path = self.temp_root / "jobs.sqlite3"
        init_job_db(self.jobs_db_path)

        self.output_dir = self.temp_root / "runs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config = {
            "max_pages": 12,
            "default_pages": 3,
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

    def _create_job(self, workflow_mode: str = "auto") -> tuple[str, Path, dict[str, object]]:
        response = self.client.post(
            "/api/jobs",
            data={
                "content": "第一页讲总览，第二页讲拆解，第三页讲行动。",
                "page_count": "3",
                "image_preset": "landscape_2k",
                "image_quality": "medium",
                "job_target": "editable_ppt",
                "workflow_mode": workflow_mode,
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
        return job_id, self.output_dir / job_id, payload

    def _seed_planned_state(self, job_id: str, job_dir: Path, *, status: str = "awaiting_plan_confirmation") -> dict[str, object]:
        pages = [
            {
                "page_no": page_no,
                "title": f"第 {page_no} 页",
                "summary": f"摘要 {page_no}",
                "bullets": [f"要点 {page_no}"],
                "layout_intent": "",
                "layout_family": "title_content",
                "page_richness": "medium",
                "reference_mode": "generation",
                "prompt_profile": "compressed",
                "status": "planned",
                "reference_image": "",
                "element_image": "",
                "reference_prompt": f"第 {page_no} 页原稿图提示词",
                "elements_prompt": f"第 {page_no} 页元素图提示词",
                "layout_slots": [],
                "texts": [],
            }
            for page_no in range(1, 4)
        ]

        def updater(state: dict[str, object]) -> None:
            state["status"] = status
            state["current_stage"] = "planning"
            state["plan"] = {
                "title": "测试规划",
                "summary": "整体摘要",
                "audience": "管理层",
                "style_type": "科技商务",
                "style_notes": "蓝白",
                "page_count": 3,
                "pages": pages,
            }
            state["pages"] = pages
            state["active_plan_version_id"] = ""
            state["plan_versions"] = []
            job_meta = state.setdefault("job_meta", {})
            job_meta["workflow_mode"] = "guided"
            job_meta["workflow_mode_label"] = "分步规划"
            job_meta["confirmation_policy"] = {"plan": True, "reference_pages": False, "element_pages": False, "export": False}
            job_meta["plan_confirmation"] = {"required": True, "confirmed": False, "status": "awaiting_confirmation"}
            for stage in state.get("stages", []):
                if isinstance(stage, dict) and stage.get("key") == "planning":
                    stage["status"] = "completed"
                    stage["summary"] = "规划已生成，等待确认后继续生成"

        mutate_job_state(job_dir, job_id, updater)
        update_job_record(
            self.jobs_db_path,
            job_id,
            status=status,
            current_stage="planning",
            stop_requested=False,
        )
        saved = load_job_state(job_id, job_dir)
        self.assertIsNotNone(saved)
        return saved

    def test_create_job_defaults_to_auto_workflow(self) -> None:
        job_id, _job_dir, payload = self._create_job()

        self.assertEqual(payload["job_meta"]["workflow_mode"], "auto")
        self.assertFalse(payload["job_meta"]["confirmation_policy"]["plan"])
        record = get_job_record(self.jobs_db_path, job_id)
        self.assertIsNotNone(record)
        self.assertEqual(record["request"]["workflow_mode"], "auto")
        self.assertEqual(record["state"]["job_meta"]["workflow_mode"], "auto")

    def test_create_guided_job_persists_confirmation_policy(self) -> None:
        job_id, _job_dir, payload = self._create_job("guided")

        self.assertEqual(payload["job_meta"]["workflow_mode"], "guided")
        self.assertTrue(payload["job_meta"]["confirmation_policy"]["plan"])
        self.assertFalse(payload["job_meta"]["plan_confirmation"]["confirmed"])
        record = get_job_record(self.jobs_db_path, job_id)
        self.assertIsNotNone(record)
        self.assertEqual(record["request"]["workflow_mode"], "guided")

    def test_plan_api_saves_draft_for_page_count_variants(self) -> None:
        job_id, job_dir, _payload = self._create_job("guided")
        self._seed_planned_state(job_id, job_dir)
        plan = {
            "title": "新版规划",
            "summary": "调整后的整体叙事",
            "audience": "销售团队",
            "style_type": "产品发布",
            "style_notes": "更轻快",
            "pages": [
                {"page_no": 3, "title": "收尾", "summary": "行动", "reference_prompt": "收尾页提示词"},
                {"page_no": 1, "title": "开场", "summary": "背景", "reference_prompt": "开场页提示词"},
                {"page_no": 2, "title": "方案", "summary": "能力", "reference_prompt": "方案页提示词"},
                {"page_no": 4, "title": "附录", "summary": "补充", "reference_prompt": "附录页提示词"},
            ],
        }

        response = self.client.put(f"/api/jobs/{job_id}/plan", json={"plan": plan})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        self.assertEqual(payload["plan"]["page_count"], 4)
        self.assertEqual([page["page_no"] for page in payload["plan"]["pages"]], [1, 2, 3, 4])
        self.assertEqual(payload["plan_confirmation"]["status"], "draft")
        self.assertEqual(payload["plan_versions"][-1]["source"], "user_draft")

        saved_state = load_job_state(job_id, job_dir)
        self.assertIsNotNone(saved_state)
        self.assertEqual(saved_state["status"], "awaiting_plan_confirmation")
        self.assertEqual(saved_state["job_meta"]["page_count"], 4)

    def test_plan_api_does_not_use_full_content_as_title(self) -> None:
        job_id, job_dir, _payload = self._create_job("guided")
        self._seed_planned_state(job_id, job_dir)

        def updater(state: dict[str, object]) -> None:
            state["plan"] = {
                "summary": "整体摘要",
                "pages": state["pages"],
            }
            job_meta = state.setdefault("job_meta", {})
            job_meta["content"] = '<p align="center"><h1 align="center">AI PPT Maker</h1></p><p>完整任务内容。</p>'

        mutate_job_state(job_dir, job_id, updater)

        response = self.client.get(f"/api/jobs/{job_id}/plan")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        self.assertEqual(payload["plan"]["title"], "AI PPT Maker")

    def test_confirm_plan_marks_confirmed_and_submits_pipeline(self) -> None:
        job_id, job_dir, _payload = self._create_job("guided")
        self._seed_planned_state(job_id, job_dir)
        initial_submit_count = len(self.executor.calls)

        response = self.client.post(f"/api/jobs/{job_id}/plan/confirm", json={})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        self.assertEqual(payload["status"], "queued")
        self.assertTrue(payload["job_meta"]["plan_confirmation"]["confirmed"])
        self.assertEqual(payload["plan_versions"][-1]["source"], "user_confirmed")
        self.assertEqual(len(self.executor.calls), initial_submit_count + 1)

        record = get_job_record(self.jobs_db_path, job_id)
        self.assertIsNotNone(record)
        self.assertEqual(record["status"], "queued")
        self.assertEqual(record["request"]["workflow_mode"], "guided")

    def test_confirm_rejects_incomplete_plan(self) -> None:
        job_id, job_dir, _payload = self._create_job("guided")
        self._seed_planned_state(job_id, job_dir)
        bad_plan = {
            "title": "缺少提示词",
            "pages": [
                {"page_no": 1, "title": "第一页", "summary": "摘要", "reference_prompt": ""},
            ],
        }

        response = self.client.post(f"/api/jobs/{job_id}/plan/confirm", json={"plan": bad_plan})

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        self.assertIn("规划", payload["error"])


if __name__ == "__main__":
    unittest.main()
