from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ppt_system.jobs.job_store import create_job, get_job, init_db
from ppt_system.web.services.job_edit_history import build_job_edit_summary
from ppt_system.web.services.job_plan_record_sync import sync_plan_metadata_to_job_record


class JobPlanRecordSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "jobs.sqlite3"
        init_db(self.db_path)
        create_job(
            self.db_path,
            {
                "job_id": "job-plan-sync",
                "status": "completed",
                "current_stage": "ppt_export",
                "title": "测试任务",
                "content": "测试内容",
                "page_count": 2,
                "image_preset": "2k",
                "image_quality": "medium",
                "style_notes": "旧风格",
                "job_dir": self.temp_dir.name,
                "request": {"style_notes": "旧风格", "page_count": 2},
                "state": {},
                "result": {},
                "stop_requested": False,
            },
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_sync_updates_history_and_resume_fields(self) -> None:
        state = {
            "job_meta": {"style_notes": "新风格", "page_count": 3},
            "plan": {"style_notes": "新风格"},
            "pages": [{"page_no": 1}, {"page_no": 2}, {"page_no": 3}],
        }
        sync_plan_metadata_to_job_record(self.db_path, "job-plan-sync", state)
        record = get_job(self.db_path, "job-plan-sync")
        self.assertEqual(record["style_notes"], "新风格")
        self.assertEqual(record["page_count"], 3)
        self.assertEqual(record["request"]["style_notes"], "新风格")
        self.assertEqual(record["request"]["page_count"], 3)

    def test_edit_summary_ignores_confirmation_without_changes(self) -> None:
        plan = {"style_notes": "蓝色", "pages": [{"page_no": 1, "title": "封面"}]}
        state = {
            "plan": plan,
            "plan_versions": [
                {"source": "model", "plan": plan, "created_at": "2026-01-01T00:00:00Z"},
                {"source": "user_confirmed", "plan": plan, "created_at": "2026-01-01T00:01:00Z"},
            ],
        }
        summary = build_job_edit_summary(state, {"style_notes": "蓝色"})
        self.assertFalse(summary["has_user_edits"])
        self.assertEqual(summary["edit_count"], 0)

    def test_edit_summary_reports_changed_plan_and_latest_style(self) -> None:
        model_plan = {"style_notes": "蓝色", "pages": [{"page_no": 1, "title": "封面"}]}
        edited_plan = {"style_notes": "蓝白高级", "pages": [{"page_no": 1, "title": "项目封面"}]}
        state = {
            "job_meta": {"style_notes": "蓝白高级"},
            "plan": edited_plan,
            "plan_versions": [
                {"source": "model", "plan": model_plan, "created_at": "2026-01-01T00:00:00Z"},
                {
                    "source": "user_confirmed",
                    "plan": edited_plan,
                    "summary": "用户调整封面和风格",
                    "created_at": "2026-01-01T00:01:00Z",
                },
            ],
        }
        summary = build_job_edit_summary(state, {"style_notes": "蓝色"})
        self.assertTrue(summary["has_user_edits"])
        self.assertEqual(summary["edit_count"], 1)
        self.assertEqual(summary["style_notes"], "蓝白高级")
        self.assertEqual(summary["last_edit_summary"], "用户调整封面和风格")


if __name__ == "__main__":
    unittest.main()
