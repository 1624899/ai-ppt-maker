from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ppt_system.export.delivery_options import EDITABLE_PPT_DELIVERY_KEY, REFERENCE_PPT_DELIVERY_KEY
from ppt_system.export.export_layer_mode import OVERLAY_LAYER_MODE, SEPARATE_LAYER_MODE
from ppt_system.jobs.job_delivery_state import attach_delivery_actions, merge_job_result


class JobDeliveryStateTests(unittest.TestCase):
    def test_merge_job_result_honors_explicit_empty_delivery_reset(self) -> None:
        existing = {
            "deliveries": {
                REFERENCE_PPT_DELIVERY_KEY: {"pptx_path": "old-reference.pptx"},
                EDITABLE_PPT_DELIVERY_KEY: {"latest": {"pptx_path": "old-editable.pptx"}},
            },
            "editable_delivery_bundle": {"bundle_path": "old-bundle.json"},
        }

        merged = merge_job_result(existing, {"deliveries": {}, "editable_delivery_bundle": {}})

        self.assertEqual(merged["deliveries"], {})
        self.assertEqual(merged["editable_delivery_bundle"], {})

    def test_merge_job_result_keeps_existing_outputs_for_incremental_delivery_update(self) -> None:
        existing = {
            "deliveries": {
                EDITABLE_PPT_DELIVERY_KEY: {
                    "latest": {"pptx_path": "old-editable.pptx"},
                    "by_layer_mode": {
                        OVERLAY_LAYER_MODE: {"pptx_path": "old-overlay.pptx"},
                    },
                }
            },
            "editable_delivery_bundle": {"bundle_path": "old-bundle.json"},
        }
        next_payload = {
            "deliveries": {
                REFERENCE_PPT_DELIVERY_KEY: {"pptx_path": "new-reference.pptx"},
            }
        }

        merged = merge_job_result(existing, next_payload)

        self.assertEqual(merged["deliveries"][REFERENCE_PPT_DELIVERY_KEY]["pptx_path"], "new-reference.pptx")
        self.assertEqual(merged["deliveries"][EDITABLE_PPT_DELIVERY_KEY]["latest"]["pptx_path"], "old-editable.pptx")
        self.assertEqual(merged["editable_delivery_bundle"]["bundle_path"], "old-bundle.json")

    def test_editable_action_downloads_when_output_file_exists_without_delivery_record(self) -> None:
        with TemporaryDirectory() as temp_dir:
            job_dir = Path(temp_dir)
            bundle_path = job_dir / "03_ppt_build" / "editable_delivery.bundle.json"
            bundle_path.parent.mkdir(parents=True)
            bundle_path.write_text(json.dumps({"project": {"pages": [{"page_no": 1}]}}, ensure_ascii=False), encoding="utf-8")
            overlay_path = job_dir / "result.editable.overlay.pptx"
            overlay_path.write_bytes(b"pptx")
            state = {
                "job_id": "job-cache-demo",
                "status": "completed",
                "pages": [{"page_no": 1}],
                "result": {
                    "editable_delivery_bundle": {
                        "bundle_path": str(bundle_path),
                        "logical_page_count": 1,
                    }
                },
            }

            enriched = attach_delivery_actions(state, job_dir)

            actions = {item["key"]: item for item in enriched["delivery_actions"]}
            self.assertTrue(actions["editable_ppt_overlay"]["generated"])
            self.assertEqual(actions["editable_ppt_overlay"]["generated_file"]["pptx_path"], str(overlay_path))
            self.assertEqual(actions["editable_ppt_overlay"]["generated_file"]["layer_mode"], OVERLAY_LAYER_MODE)
            self.assertFalse(actions["editable_ppt_separate"]["generated"])

    def test_editable_action_regenerates_when_delivery_record_points_to_missing_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            job_dir = Path(temp_dir)
            bundle_path = job_dir / "03_ppt_build" / "editable_delivery.bundle.json"
            bundle_path.parent.mkdir(parents=True)
            bundle_path.write_text(json.dumps({"project": {"pages": [{"page_no": 1}]}}, ensure_ascii=False), encoding="utf-8")
            missing_path = job_dir / "result.editable.separate_slides.pptx"
            state = {
                "job_id": "job-missing-demo",
                "status": "completed",
                "pages": [{"page_no": 1}],
                "result": {
                    "editable_delivery_bundle": {
                        "bundle_path": str(bundle_path),
                        "logical_page_count": 1,
                    },
                    "deliveries": {
                        "editable_ppt": {
                            "by_layer_mode": {
                                SEPARATE_LAYER_MODE: {
                                    "pptx_path": str(missing_path),
                                    "pptx_url": "/runs/job-missing-demo/result.editable.separate_slides.pptx",
                                    "layer_mode": SEPARATE_LAYER_MODE,
                                }
                            }
                        }
                    },
                },
            }

            enriched = attach_delivery_actions(state, job_dir)

            actions = {item["key"]: item for item in enriched["delivery_actions"]}
            self.assertFalse(actions["editable_ppt_separate"]["generated"])
            self.assertEqual(actions["editable_ppt_separate"]["generated_file"], {})


if __name__ == "__main__":
    unittest.main()
