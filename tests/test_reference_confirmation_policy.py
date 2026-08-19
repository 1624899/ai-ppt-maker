from __future__ import annotations

import unittest

from ppt_system.web.services.workflow_policy import ensure_workflow_metadata, should_pause_after_reference


class ReferenceConfirmationPolicyTests(unittest.TestCase):
    def test_old_guided_job_with_elements_is_inferred_as_confirmed(self):
        state = {
            "job_meta": {"workflow_mode": "guided"},
            "element_pages": [{"page_no": 1, "image": "/runs/job/element.png"}],
            "stages": [],
        }
        ensure_workflow_metadata(state)
        confirmation = state["job_meta"]["reference_confirmation"]
        self.assertTrue(confirmation["confirmed"])
        self.assertEqual(confirmation["status"], "inferred_from_existing_outputs")
        self.assertFalse(should_pause_after_reference(state))

    def test_new_guided_job_without_downstream_outputs_still_pauses(self):
        state = {"job_meta": {"workflow_mode": "guided"}, "element_pages": [], "stages": []}
        ensure_workflow_metadata(state)
        self.assertFalse(state["job_meta"]["reference_confirmation"]["confirmed"])
        self.assertTrue(should_pause_after_reference(state))


if __name__ == "__main__":
    unittest.main()
