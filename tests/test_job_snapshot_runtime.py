from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ppt_system.web.services.job_snapshot_runtime import (
    build_job_payload,
    build_job_payload_from_state,
    write_job_snapshot,
)


class _Provider:
    model = "model"
    api_base_url = "https://example.com/v1"


class JobSnapshotRuntimeTests(unittest.TestCase):
    def test_build_job_payload_from_state_preserves_image_edit_candidates(self) -> None:
        state = {
            "job_id": "job-test",
            "plan": {"pages": []},
            "pages": [{"page_no": 1, "reference_image": "/runs/job-test/01_reference_pages/page_01_reference.png"}],
            "reference_pages": [],
            "element_pages": [],
            "result": {},
            "image_edit_candidates": [{"candidate_id": "candidate-new", "status": "generated"}],
        }
        snapshot = {
            "job_id": "job-test",
            "mode": "openai",
            "content": "旧内容",
            "image_edit_candidates": [{"candidate_id": "candidate-old", "status": "generated"}],
        }

        payload = build_job_payload_from_state(state, snapshot)

        self.assertEqual(payload["image_edit_candidates"], state["image_edit_candidates"])

    def test_write_job_snapshot_keeps_runtime_extensions_from_existing_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            job_dir = Path(temp_dir)
            candidate = {"candidate_id": "candidate-kept", "status": "applied"}
            (job_dir / "job.json").write_text(
                json.dumps(
                    {
                        "job_id": "job-test",
                        "mode": "openai",
                        "content": "旧内容",
                        "image_edit_candidates": [candidate],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            payload = build_job_payload(
                job_id="job-test",
                config={"generation_mode": "openai"},
                content="新内容",
                plan={"pages": []},
                pages=[],
                references=[],
                element_pages=[],
                chat_provider=_Provider(),
                chat_profile={},
                image_provider=_Provider(),
                image_profile={},
                result_payload={},
            )
            write_job_snapshot(job_dir, payload)

            saved = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["content"], "新内容")
            self.assertEqual(saved["image_edit_candidates"], [candidate])

    def test_build_job_payload_can_take_runtime_extensions_from_state(self) -> None:
        candidate = {"candidate_id": "candidate-state", "status": "generated"}

        payload = build_job_payload(
            job_id="job-test",
            config={"generation_mode": "openai"},
            content="内容",
            plan={"pages": []},
            pages=[],
            references=[],
            element_pages=[],
            chat_provider=_Provider(),
            chat_profile={},
            image_provider=_Provider(),
            image_profile={},
            result_payload={},
            runtime_state={"image_edit_candidates": [candidate]},
        )

        self.assertEqual(payload["image_edit_candidates"], [candidate])


if __name__ == "__main__":
    unittest.main()
