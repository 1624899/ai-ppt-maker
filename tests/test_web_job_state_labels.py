from __future__ import annotations

import unittest

from web_app import enrich_job_state_with_record


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


if __name__ == "__main__":
    unittest.main()
