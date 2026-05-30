from __future__ import annotations

import unittest

from ppt_system.web.services.job_state_runtime import job_summary
from main import enrich_job_state_with_record


class WebJobStateLabelTests(unittest.TestCase):
    def test_enrich_job_state_with_record_normalizes_corrupted_stage_labels(self) -> None:
        state = {
            "job_id": "demo",
            "job_meta": {},
            "stages": [
                {"key": "planning", "label": "?????", "status": "completed", "summary": ""},
                {"key": "ppt_export", "label": "PPT ??", "status": "running", "summary": ""},
            ],
        }

        result = enrich_job_state_with_record(state, None)

        self.assertEqual(result["stages"][0]["label"], "模型规划")
        self.assertEqual(result["stages"][1]["label"], "可编辑元素生成")

    def test_enrich_job_state_prefers_record_runtime_status(self) -> None:
        state = {
            "job_id": "demo",
            "status": "queued",
            "current_stage": "reference_generation",
            "stop_requested": True,
            "job_meta": {},
            "stages": [
                {"key": "planning", "status": "completed", "summary": ""},
                {"key": "ppt_export", "status": "pending", "summary": ""},
            ],
        }
        record = {
            "job_id": "demo",
            "status": "error",
            "current_stage": "ppt_export",
            "stop_requested": False,
            "title": "演示任务",
            "content": "演示内容",
            "page_count": 1,
            "image_quality": "medium",
            "style_notes": "",
            "request": {},
            "job_dir": ".",
        }

        result = enrich_job_state_with_record(state, record)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["current_stage"], "ppt_export")
        self.assertFalse(result["stop_requested"])

    def test_enrich_job_state_reconciles_terminal_stage_status(self) -> None:
        state = {
            "job_id": "demo",
            "status": "queued",
            "current_stage": "ppt_export",
            "error": "",
            "stop_requested": True,
            "job_meta": {},
            "stages": [
                {"key": "planning", "status": "completed", "summary": ""},
                {"key": "ppt_export", "status": "error", "summary": "导出失败"},
            ],
        }

        result = enrich_job_state_with_record(state, None)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["current_stage"], "ppt_export")
        self.assertFalse(result["stop_requested"])
        self.assertEqual(result["error"], "导出失败")

    def test_job_summary_uses_generated_artifacts_as_preview_image(self) -> None:
        record = {
            "job_id": "demo",
            "title": "演示任务",
            "status": "completed",
            "current_stage": "ppt_export",
            "page_count": 2,
            "image_preset": "wide",
            "image_quality": "medium",
            "style_notes": "",
            "created_at": "2026-05-30 10:00:00",
            "updated_at": "2026-05-30 10:01:00",
            "state": {
                "pages": [
                    {"page_no": 1, "title": "第一页"},
                    {"page_no": 2, "title": "第二页", "reference_image": "/runs/demo/page_02_reference.png"},
                ],
                "reference_pages": [{"page_no": 1, "image": "/runs/demo/page_01_reference.png"}],
                "element_pages": [{"page_no": 1, "image": "/runs/demo/page_01_elements.png"}],
            },
        }

        result = job_summary(record)

        self.assertEqual(result["preview_image"], "/runs/demo/page_01_elements.png")


if __name__ == "__main__":
    unittest.main()
