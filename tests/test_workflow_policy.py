from __future__ import annotations

import unittest

from ppt_system.web.services.workflow_policy import (
    AWAITING_PLAN_CONFIRMATION_STATUS,
    build_confirmation_policy,
    initial_plan_confirmation_state,
    mark_awaiting_plan_confirmation,
    mark_plan_confirmed,
    mark_plan_draft,
    normalize_workflow_mode,
    should_pause_after_planning,
)


class WorkflowPolicyTests(unittest.TestCase):
    def test_normalize_workflow_mode_falls_back_to_auto(self) -> None:
        self.assertEqual(normalize_workflow_mode("guided"), "guided")
        self.assertEqual(normalize_workflow_mode("AUTO"), "auto")
        self.assertEqual(normalize_workflow_mode("unknown"), "auto")
        self.assertEqual(normalize_workflow_mode(None), "auto")

    def test_confirmation_policy_is_driven_by_mode_and_overrides(self) -> None:
        self.assertFalse(build_confirmation_policy("auto")["plan"])
        self.assertTrue(build_confirmation_policy("guided")["plan"])
        policy = build_confirmation_policy("guided", {"plan": False, "reference_pages": True})
        self.assertFalse(policy["plan"])
        self.assertTrue(policy["reference_pages"])

    def test_guided_plan_confirmation_lifecycle(self) -> None:
        state = {
            "status": "queued",
            "current_stage": "planning",
            "job_meta": {
                "workflow_mode": "guided",
                "confirmation_policy": build_confirmation_policy("guided"),
                "plan_confirmation": initial_plan_confirmation_state("guided"),
            },
        }

        self.assertTrue(should_pause_after_planning(state))
        mark_awaiting_plan_confirmation(state)
        self.assertEqual(state["status"], AWAITING_PLAN_CONFIRMATION_STATUS)
        self.assertEqual(state["job_meta"]["plan_confirmation"]["status"], "awaiting_confirmation")

        mark_plan_draft(state)
        self.assertTrue(should_pause_after_planning(state))
        self.assertEqual(state["job_meta"]["plan_confirmation"]["status"], "draft")

        mark_plan_confirmed(state)
        self.assertFalse(should_pause_after_planning(state))
        self.assertTrue(state["job_meta"]["plan_confirmation"]["confirmed"])

    def test_auto_mode_never_pauses_after_planning(self) -> None:
        state = {
            "job_meta": {
                "workflow_mode": "auto",
                "confirmation_policy": build_confirmation_policy("auto"),
                "plan_confirmation": initial_plan_confirmation_state("auto"),
            }
        }

        self.assertFalse(should_pause_after_planning(state))


if __name__ == "__main__":
    unittest.main()
