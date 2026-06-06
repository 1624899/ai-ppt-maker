from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import main
from ppt_system.jobs.job_store import get_job as get_job_record
from ppt_system.jobs.job_store import init_db as init_job_db
from main import app, mutate_job_state, update_job_record


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
                "reference_prompt": f"原稿图提示词 {page_no}",
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
                    "stages": [
                        {
                            **stage,
                            "status": "completed",
                            "summary": stage.get("summary") or "测试任务已完成",
                        }
                        for stage in state.get("stages", [])
                    ],
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

    def test_agent_style_instruction_requeues_pipeline_for_whole_deck(self) -> None:
        job_id, job_dir = self._seed_completed_pages()
        initial_submit_count = len(self.executor.calls)

        response = self.client.post(
            f"/api/jobs/{job_id}/operations",
            json={"operation_type": "agent_instruction", "instruction": "整体改成更商务的蓝白风格"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        self.assertEqual(len(self.executor.calls), initial_submit_count + 1)
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["current_stage"], "reference_generation")
        self.assertEqual(payload["operations"][-1]["status"], "submitted")
        self.assertEqual(payload["operations"][-1]["execution"], "pipeline")
        self.assertEqual(payload["operations"][-1]["edit_kind"], "style")
        self.assertEqual(payload["operations"][-1]["affected_pages"], [1, 2])
        self.assertEqual([item["page_no"] for item in payload["reference_pages"]], [])
        self.assertEqual([item["page_no"] for item in payload["element_pages"]], [])
        self.assertEqual(len(payload["page_versions"]), 2)
        self.assertTrue((job_dir / "versions" / "page_01" / payload["page_versions"][0]["version_id"] / "reference.png").exists())

    def test_ambiguous_agent_instruction_is_recorded_without_submitting_pipeline(self) -> None:
        job_id, _job_dir = self._seed_completed_pages()
        initial_submit_count = len(self.executor.calls)

        response = self.client.post(
            f"/api/jobs/{job_id}/operations",
            json={"operation_type": "agent_instruction", "instruction": "帮我看看这份 PPT 有没有问题"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        self.assertEqual(len(self.executor.calls), initial_submit_count)
        self.assertEqual(payload["operations"][-1]["status"], "accepted")
        self.assertEqual(payload["operations"][-1]["execution"], "pending_backend")

    def test_agent_draft_requires_chat_model_config(self) -> None:
        job_id, _job_dir = self._seed_completed_pages()
        initial_submit_count = len(self.executor.calls)

        response = self.client.post(
            f"/api/jobs/{job_id}/agent/draft",
            json={
                "message": "这里看着有点乱，右边那块太挤了，改得更清楚一点",
                "page_no": 2,
                "preview_type": "reference",
                "annotations": [
                    {
                        "id": "box-1",
                        "label": "右侧信息区",
                        "box": {"x": 0.62, "y": 0.22, "width": 0.25, "height": 0.46},
                    }
                ],
            },
        )

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        self.assertIn("对话模型", payload["error"])
        self.assertEqual(len(self.executor.calls), initial_submit_count)

    def test_agent_draft_model_error_is_not_replaced_by_rule_answer(self) -> None:
        job_id, _job_dir = self._seed_completed_pages()
        config = {
            **self.config,
            "model_configs": {
                "chat": [
                    {
                        "id": "chat_agent",
                        "name": "Agent 对话模型",
                        "base_url": "https://example.com/v1",
                        "api_key": "sk-test",
                        "model": "agent-model",
                    }
                ],
                "image": [],
            },
            "active_chat_config_id": "chat_agent",
        }

        class FailingAgentProvider:
            def __init__(self, provider_config, profile) -> None:
                pass

            def build_image_message_item(self, image_path: Path) -> dict[str, object]:
                return {"type": "image_url", "image_url": {"url": "data:image/png;base64,stub"}}

            def complete_json(self, messages):
                raise RuntimeError("上游模型不可用")

        with patch.object(main, "read_config", return_value=config), patch(
            "ppt_system.web.services.job_agent_draft_model_planner.OpenAIChatProvider",
            FailingAgentProvider,
        ):
            response = self.client.post(
                f"/api/jobs/{job_id}/agent/draft",
                json={"message": "整体改成更商务的蓝白科技风"},
            )

        self.assertEqual(response.status_code, 502)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        self.assertIn("上游模型不可用", payload["error"])

    def test_agent_conversation_can_be_cleared(self) -> None:
        job_id, _job_dir = self._seed_completed_pages()
        config = {
            **self.config,
            "model_configs": {
                "chat": [
                    {
                        "id": "chat_agent",
                        "name": "Agent 对话模型",
                        "base_url": "https://example.com/v1",
                        "api_key": "sk-test",
                        "model": "agent-model",
                    }
                ],
                "image": [],
            },
            "active_chat_config_id": "chat_agent",
        }

        class FakeAgentProvider:
            def __init__(self, provider_config, profile) -> None:
                pass

            def build_image_message_item(self, image_path: Path) -> dict[str, object]:
                return {"type": "image_url", "image_url": {"url": "data:image/png;base64,stub"}}

            def complete_json(self, messages):
                return {
                    "edit_kind": "style",
                    "affected_pages": [1, 2],
                    "summary": "我理解为整套 PPT 要统一成更商务的蓝白科技风。",
                    "changes": ["统一配色", "降低装饰密度"],
                    "instruction": "整套 PPT 风格调整为更商务的蓝白科技风。",
                    "confidence": "high",
                }

        with patch.object(main, "read_config", return_value=config), patch(
            "ppt_system.web.services.job_agent_draft_model_planner.OpenAIChatProvider",
            FakeAgentProvider,
        ):
            draft_response = self.client.post(
                f"/api/jobs/{job_id}/agent/draft",
                json={"message": "整体改成更商务的蓝白科技风"},
            )
        self.assertEqual(draft_response.status_code, 200)

        response = self.client.delete(f"/api/jobs/{job_id}/agent/conversation")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        self.assertEqual(payload["messages"], [])
        self.assertIsNone(payload["agent_pending_draft"])

        status_response = self.client.get(f"/api/jobs/{job_id}")
        self.assertEqual(status_response.status_code, 200)
        status_payload = status_response.get_json()
        self.assertIsNotNone(status_payload)
        self.assertEqual(status_payload.get("agent_conversation"), [])
        self.assertIsNone(status_payload.get("agent_pending_draft"))

    def test_agent_draft_uses_chat_model_when_configured(self) -> None:
        job_id, _job_dir = self._seed_completed_pages()
        config = {
            **self.config,
            "model_configs": {
                "chat": [
                    {
                        "id": "chat_agent",
                        "name": "Agent 对话模型",
                        "base_url": "https://example.com/v1",
                        "api_key": "sk-test",
                        "model": "agent-model",
                        "temperature": 0.1,
                        "max_tokens": 800,
                    }
                ],
                "image": [],
            },
            "active_chat_config_id": "chat_agent",
        }
        captured: dict[str, object] = {}

        class FakeAgentProvider:
            def __init__(self, provider_config, profile) -> None:
                captured["profile"] = profile
                captured["config"] = provider_config

            def build_image_message_item(self, image_path: Path) -> dict[str, object]:
                captured["image_path"] = image_path
                return {"type": "image_url", "image_url": {"url": "data:image/png;base64,stub"}}

            def complete_json(self, messages):
                captured["messages"] = messages
                return {
                    "edit_kind": "layout",
                    "affected_pages": [2],
                    "summary": "我理解为第 2 页右侧信息区层级太弱，需要重新整理。",
                    "changes": ["压缩右侧模块文字密度", "拉开卡片层级并增强留白"],
                    "instruction": "第 2 页画面与排版修改：右侧信息区更清晰、更像咨询汇报。",
                    "confidence": "high",
                }

        with patch.object(main, "read_config", return_value=config), patch(
            "ppt_system.web.services.job_agent_draft_model_planner.OpenAIChatProvider",
            FakeAgentProvider,
        ):
            response = self.client.post(
                f"/api/jobs/{job_id}/agent/draft",
                json={
                    "message": "右边那块太乱了，要更像咨询汇报",
                    "page_no": 2,
                    "preview_type": "reference",
                    "messages": [{"role": "assistant", "message": "可以，我先理解问题。"}],
                    "annotations": [
                        {
                            "id": "box-1",
                            "label": "右侧信息区",
                            "box": {"x": 0.58, "y": 0.18, "width": 0.3, "height": 0.5},
                        }
                    ],
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        draft = payload["draft"]
        self.assertEqual(payload["agent_meta"]["planner"], "model")
        self.assertEqual(draft["operation_type"], "page_layout_optimize")
        self.assertEqual(draft["edit_kind"], "layout")
        self.assertEqual(draft["affected_pages"], [2])
        self.assertIn("右侧信息区", draft["instruction"])
        model_messages = captured["messages"]
        self.assertIsInstance(model_messages, list)
        user_content = model_messages[1]["content"]
        self.assertTrue(any(item.get("type") == "image_url" for item in user_content))
        prompt_text = next(item["text"] for item in user_content if item.get("type") == "text")
        self.assertIn("右边那块太乱了", prompt_text)
        self.assertIn("右侧信息区", prompt_text)
        self.assertIn("可以，我先理解问题。", prompt_text)

    def test_page_text_optimize_rebuilds_export_without_invalidating_images(self) -> None:
        job_id, _job_dir = self._seed_completed_pages()
        initial_submit_count = len(self.executor.calls)

        response = self.client.post(
            f"/api/jobs/{job_id}/operations",
            json={"operation_type": "page_text_optimize", "page_no": 2, "instruction": "第二页减少文字，正文压缩到 3 个要点"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        self.assertEqual(len(self.executor.calls), initial_submit_count + 1)
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["current_stage"], "ppt_export")
        self.assertEqual(payload["operations"][-1]["edit_kind"], "text")
        self.assertEqual(payload["operations"][-1]["affected_pages"], [2])

        page_two = next(page for page in payload["pages"] if int(page["page_no"]) == 2)
        self.assertTrue(page_two["reference_image"])
        self.assertTrue(page_two["element_image"])
        self.assertLessEqual(len(page_two["bullets"]), 3)
        self.assertTrue(page_two["texts"])
        self.assertEqual([item["page_no"] for item in payload["reference_pages"]], [1, 2])
        self.assertEqual([item["page_no"] for item in payload["element_pages"]], [1, 2])

    def test_page_layout_optimize_updates_plan_and_invalidates_target_page(self) -> None:
        job_id, _job_dir = self._seed_completed_pages()
        initial_submit_count = len(self.executor.calls)

        response = self.client.post(
            f"/api/jobs/{job_id}/operations",
            json={"operation_type": "page_layout_optimize", "page_no": 2, "instruction": "第二页改为流程图，并且更留白"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        self.assertEqual(len(self.executor.calls), initial_submit_count + 1)
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["current_stage"], "reference_generation")
        self.assertEqual(payload["operations"][-1]["edit_kind"], "layout")

        page_two = next(page for page in payload["pages"] if int(page["page_no"]) == 2)
        self.assertEqual(page_two["layout_family"], "process_horizontal")
        self.assertEqual(page_two["page_richness"], "low")
        self.assertEqual(page_two["reference_image"], "")
        self.assertEqual(page_two["element_image"], "")
        self.assertEqual([item["page_no"] for item in payload["reference_pages"]], [1])
        self.assertEqual([item["page_no"] for item in payload["element_pages"]], [1])

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

    def test_image_edit_candidate_generation_does_not_replace_current_image(self) -> None:
        job_id, _job_dir = self._seed_completed_pages()
        config = {
            **self.config,
            "model_configs": {
                "chat": [],
                "image": [
                    {
                        "id": "image_editor",
                        "name": "图片编辑模型",
                        "base_url": "https://example.com/v1",
                        "api_key": "sk-test",
                        "model": "image-model",
                    }
                ],
            },
            "active_image_config_id": "image_editor",
        }
        captured: dict[str, object] = {}

        class FakeImageProvider:
            def __init__(self, provider_config, profile) -> None:
                captured["config"] = provider_config
                captured["profile"] = profile

            def generate_edited_image(self, prompt: str, output_path: Path, image_paths: list[Path]) -> dict[str, object]:
                captured["prompt"] = prompt
                captured["image_paths"] = image_paths
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"candidate-image")
                return {"provider": "fake", "input_images": [str(path) for path in image_paths]}

        with patch.object(main, "read_config", return_value=config), patch(
            "ppt_system.web.services.job_image_edit_service.OpenAIImageProvider",
            FakeImageProvider,
        ):
            response = self.client.post(
                f"/api/jobs/{job_id}/image-edit-candidates",
                json={
                    "page_no": 2,
                    "preview_type": "reference",
                    "instruction": "右侧模块更清晰，标题更短",
                    "annotations": [
                        {
                            "id": "box-1",
                            "label": "右侧模块",
                            "box": {"x": 0.55, "y": 0.2, "width": 0.28, "height": 0.5},
                        }
                    ],
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        page_two = next(page for page in payload["pages"] if int(page["page_no"]) == 2)
        self.assertEqual(page_two["reference_image"], f"/runs/{job_id}/01_reference_pages/page_02_reference.png")
        self.assertEqual(page_two["element_image"], f"/runs/{job_id}/02_elements_pages/page_02_elements.png")
        self.assertEqual([item["page_no"] for item in payload["reference_pages"]], [1, 2])
        self.assertEqual([item["page_no"] for item in payload["element_pages"]], [1, 2])
        self.assertEqual(len(payload["image_edit_candidates"]), 1)
        candidate = payload["image_edit_candidates"][0]
        self.assertEqual(candidate["status"], "generated")
        self.assertEqual(candidate["preview_type"], "reference")
        self.assertIn("04_image_edits/page_02", candidate["image"])
        self.assertIn("右侧模块", captured["prompt"])
        self.assertEqual(Path(captured["image_paths"][0]).name, "page_02_reference.png")

    def test_apply_image_edit_candidate_replaces_reference_after_confirmation(self) -> None:
        job_id, job_dir = self._seed_completed_pages()
        config = {
            **self.config,
            "model_configs": {
                "chat": [],
                "image": [
                    {
                        "id": "image_editor",
                        "name": "图片编辑模型",
                        "base_url": "https://example.com/v1",
                        "api_key": "sk-test",
                        "model": "image-model",
                    }
                ],
            },
            "active_image_config_id": "image_editor",
        }

        class FakeImageProvider:
            def __init__(self, provider_config, profile) -> None:
                pass

            def generate_edited_image(self, prompt: str, output_path: Path, image_paths: list[Path]) -> dict[str, object]:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"candidate-image")
                return {"provider": "fake"}

        with patch.object(main, "read_config", return_value=config), patch(
            "ppt_system.web.services.job_image_edit_service.OpenAIImageProvider",
            FakeImageProvider,
        ):
            candidate_response = self.client.post(
                f"/api/jobs/{job_id}/image-edit-candidates",
                json={"page_no": 2, "preview_type": "reference", "instruction": "右侧模块更清晰"},
            )
        self.assertEqual(candidate_response.status_code, 200)
        candidate_payload = candidate_response.get_json()
        self.assertIsNotNone(candidate_payload)
        candidate_id = candidate_payload["image_edit_candidates"][0]["candidate_id"]
        candidate_image = candidate_payload["image_edit_candidates"][0]["image"]

        apply_response = self.client.post(f"/api/jobs/{job_id}/image-edit-candidates/{candidate_id}/apply")

        self.assertEqual(apply_response.status_code, 200)
        payload = apply_response.get_json()
        self.assertIsNotNone(payload)
        page_two = next(page for page in payload["pages"] if int(page["page_no"]) == 2)
        self.assertEqual(page_two["reference_image"], candidate_image)
        self.assertEqual(page_two["element_image"], "")
        self.assertEqual([item["page_no"] for item in payload["reference_pages"]], [1, 2])
        edited_reference = next(item for item in payload["reference_pages"] if int(item["page_no"]) == 2)
        self.assertEqual(edited_reference["image"], candidate_image)
        self.assertEqual([item["page_no"] for item in payload["element_pages"]], [1])
        applied_candidate = payload["image_edit_candidates"][0]
        self.assertEqual(applied_candidate["status"], "applied")
        self.assertEqual(payload["operations"][-1]["type"], "image_edit_apply")
        self.assertEqual(payload["result"], {"deliveries": {}, "editable_delivery_bundle": {}})
        self.assertTrue((job_dir / "versions" / "page_02" / applied_candidate["version_id"] / "reference.png").exists())
        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["current_stage"], "elements_generation")
        stages_by_key = {stage["key"]: stage for stage in payload["stages"]}
        self.assertEqual(stages_by_key["elements_generation"]["status"], "running")
        self.assertEqual(stages_by_key["ppt_export"]["status"], "pending")
        record = get_job_record(self.jobs_db_path, job_id)
        self.assertIsNotNone(record)
        self.assertEqual(record["status"], "running")
        self.assertEqual(record["current_stage"], "elements_generation")
        self.assertEqual(len(self.executor.calls), 2)

    def test_apply_image_edit_candidate_replaces_element_and_requeues_export_only(self) -> None:
        job_id, _job_dir = self._seed_completed_pages()
        config = {
            **self.config,
            "model_configs": {
                "chat": [],
                "image": [
                    {
                        "id": "image_editor",
                        "name": "图片编辑模型",
                        "base_url": "https://example.com/v1",
                        "api_key": "sk-test",
                        "model": "image-model",
                    }
                ],
            },
            "active_image_config_id": "image_editor",
        }

        class FakeImageProvider:
            def __init__(self, provider_config, profile) -> None:
                pass

            def generate_edited_image(self, prompt: str, output_path: Path, image_paths: list[Path]) -> dict[str, object]:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"candidate-image")
                return {"provider": "fake"}

        with patch.object(main, "read_config", return_value=config), patch(
            "ppt_system.web.services.job_image_edit_service.OpenAIImageProvider",
            FakeImageProvider,
        ):
            candidate_response = self.client.post(
                f"/api/jobs/{job_id}/image-edit-candidates",
                json={"page_no": 2, "preview_type": "element", "instruction": "图标更清晰"},
            )
        self.assertEqual(candidate_response.status_code, 200)
        candidate_payload = candidate_response.get_json()
        self.assertIsNotNone(candidate_payload)
        candidate_id = candidate_payload["image_edit_candidates"][0]["candidate_id"]
        candidate_image = candidate_payload["image_edit_candidates"][0]["image"]

        apply_response = self.client.post(f"/api/jobs/{job_id}/image-edit-candidates/{candidate_id}/apply")

        self.assertEqual(apply_response.status_code, 200)
        payload = apply_response.get_json()
        self.assertIsNotNone(payload)
        page_two = next(page for page in payload["pages"] if int(page["page_no"]) == 2)
        self.assertEqual(page_two["element_image"], candidate_image)
        self.assertEqual([item["page_no"] for item in payload["reference_pages"]], [1, 2])
        self.assertEqual([item["page_no"] for item in payload["element_pages"]], [1, 2])
        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["current_stage"], "ppt_export")
        stages_by_key = {stage["key"]: stage for stage in payload["stages"]}
        self.assertEqual(stages_by_key["reference_generation"]["status"], "completed")
        self.assertEqual(stages_by_key["elements_generation"]["status"], "completed")
        self.assertEqual(stages_by_key["ppt_export"]["status"], "running")
        record = get_job_record(self.jobs_db_path, job_id)
        self.assertIsNotNone(record)
        self.assertEqual(record["status"], "running")
        self.assertEqual(record["current_stage"], "ppt_export")
        self.assertEqual(len(self.executor.calls), 2)

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
