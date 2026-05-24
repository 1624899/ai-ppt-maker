from __future__ import annotations

import unittest

from ppt_system.stage_resume import has_expected_outputs, reconcile_completed_stages, should_run_stage


class StageResumeTests(unittest.TestCase):
    def test_completed_stage_with_ready_outputs_keeps_completed_state(self) -> None:
        state = {
            "stages": [
                {"key": "planning", "status": "completed"},
            ]
        }

        self.assertFalse(
            should_run_stage(state, "planning", output_ready=True)
        )

    def test_completed_stage_without_outputs_must_rebuild(self) -> None:
        state = {
            "stages": [
                {"key": "planning", "status": "completed"},
            ]
        }

        self.assertTrue(
            should_run_stage(state, "planning", output_ready=False)
        )

    def test_non_completed_stage_with_outputs_still_runs(self) -> None:
        state = {
            "stages": [
                {"key": "reference_generation", "status": "interrupted"},
            ]
        }

        self.assertTrue(
            should_run_stage(state, "reference_generation", output_ready=True)
        )

    def test_has_expected_outputs_requires_full_count(self) -> None:
        self.assertTrue(has_expected_outputs([1, 2, 3], 3))
        self.assertFalse(has_expected_outputs([1, 2], 3))
        self.assertFalse(has_expected_outputs([], 0))

    def test_reconcile_completed_stages_repairs_historical_dirty_state(self) -> None:
        state = {
            "stages": [
                {"key": "planning", "status": "running"},
                {"key": "reference_generation", "status": "completed"},
                {"key": "elements_generation", "status": "running"},
            ]
        }

        changed = reconcile_completed_stages(
            state,
            {
                "planning": True,
                "reference_generation": True,
                "elements_generation": True,
            },
        )

        self.assertTrue(changed)
        self.assertEqual(state["stages"][0]["status"], "completed")
        self.assertEqual(state["stages"][2]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
