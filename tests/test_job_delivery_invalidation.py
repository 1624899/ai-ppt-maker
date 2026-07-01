from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from ppt_system.export.delivery_options import EDITABLE_PPT_FILENAMES, REFERENCE_PPT_FILENAME
from ppt_system.export.editable_delivery_cache import build_editable_delivery_cache_path
from ppt_system.web.services.job_delivery_invalidation import (
    DeliveryInvalidationError,
    build_delivery_artifact_paths,
    build_empty_delivery_result,
    invalidate_delivery_artifacts,
    invalidate_delivery_result,
    remove_stale_delivery_files,
)


class JobDeliveryInvalidationTests(unittest.TestCase):
    def test_remove_stale_delivery_files_deletes_known_pptx_outputs_and_cache_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            job_dir = Path(temp_dir)
            stale_paths = _write_stale_delivery_files(job_dir)

            summary = remove_stale_delivery_files(job_dir, include_reference=True)

            for path in stale_paths:
                self.assertFalse(path.exists(), f"旧交付文件未删除：{path.name}")
            self.assertEqual(set(summary.removed), set(stale_paths))
            self.assertEqual(summary.failed, ())

    def test_remove_stale_delivery_files_can_target_editable_outputs_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            job_dir = Path(temp_dir)
            stale_paths = _write_stale_delivery_files(job_dir)
            reference_path = job_dir / REFERENCE_PPT_FILENAME

            remove_stale_delivery_files(job_dir, include_reference=False)

            self.assertTrue(reference_path.exists())
            for path in stale_paths:
                if path == reference_path:
                    continue
                self.assertFalse(path.exists(), f"旧可编辑交付文件未删除：{path.name}")

    def test_invalidate_delivery_artifacts_clears_state_snapshot_record_and_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            job_dir = Path(temp_dir)
            stale_paths = _write_stale_delivery_files(job_dir)
            state = {"result": {"deliveries": {"reference_ppt": {"pptx_path": "old"}}}}
            written_snapshot: dict[str, Any] = {}
            updated_jobs: list[tuple[str, dict[str, Any]]] = []

            def fake_write_snapshot(_job_dir: Path, snapshot: dict[str, Any]) -> None:
                written_snapshot.update(json.loads(json.dumps(snapshot, ensure_ascii=False)))

            def fake_update_job_record(_db_path: Path, job_id: str, **fields: Any) -> None:
                updated_jobs.append((job_id, fields))

            with patch(
                "ppt_system.web.services.job_delivery_invalidation.load_job_snapshot",
                return_value={"result": {"deliveries": {"editable_ppt": {"latest": {}}}}},
            ), patch(
                "ppt_system.web.services.job_delivery_invalidation.write_job_snapshot",
                side_effect=fake_write_snapshot,
            ), patch(
                "ppt_system.web.services.job_delivery_invalidation.update_job_record",
                side_effect=fake_update_job_record,
            ):
                summary = invalidate_delivery_artifacts(
                    job_dir,
                    job_id="job-demo",
                    state=state,
                    include_reference=True,
                )

            self.assertEqual(state["result"], build_empty_delivery_result())
            self.assertEqual(written_snapshot["result"], build_empty_delivery_result())
            self.assertEqual(updated_jobs[0][0], "job-demo")
            self.assertEqual(updated_jobs[0][1]["result"], build_empty_delivery_result())
            for path in stale_paths:
                self.assertFalse(path.exists(), f"旧交付文件未删除：{path.name}")
            self.assertEqual(set(summary.removed), set(stale_paths))

    def test_invalidate_delivery_artifacts_keeps_state_when_file_removal_fails(self) -> None:
        with TemporaryDirectory() as temp_dir:
            job_dir = Path(temp_dir)
            stale_paths = _write_stale_delivery_files(job_dir)
            state = {"result": {"deliveries": {"reference_ppt": {"pptx_path": "old"}}}}
            written_snapshots: list[dict[str, Any]] = []
            updated_jobs: list[tuple[str, dict[str, Any]]] = []

            with patch.object(Path, "unlink", side_effect=OSError("文件被占用")):
                with self.assertRaises(DeliveryInvalidationError) as context:
                    with patch(
                        "ppt_system.web.services.job_delivery_invalidation.write_job_snapshot",
                        side_effect=lambda _job_dir, snapshot: written_snapshots.append(snapshot),
                    ), patch(
                        "ppt_system.web.services.job_delivery_invalidation.update_job_record",
                        side_effect=lambda _db_path, job_id, **fields: updated_jobs.append((job_id, fields)),
                    ):
                        invalidate_delivery_artifacts(
                            job_dir,
                            job_id="job-demo",
                            state=state,
                            include_reference=True,
                        )

            self.assertEqual(set(context.exception.summary.failed), set(stale_paths))
            self.assertEqual(state["result"], {"deliveries": {"reference_ppt": {"pptx_path": "old"}}})
            self.assertEqual(written_snapshots, [])
            self.assertEqual(updated_jobs, [])
            for path in stale_paths:
                self.assertTrue(path.exists(), f"删除失败时不应清理文件记录：{path.name}")

    def test_invalidate_delivery_result_uses_fresh_payload(self) -> None:
        state_a: dict[str, Any] = {}
        state_b: dict[str, Any] = {}

        invalidate_delivery_result(state_a)
        invalidate_delivery_result(state_b)
        state_a["result"]["deliveries"]["demo"] = {"pptx_path": "old.pptx"}

        self.assertEqual(state_b["result"], build_empty_delivery_result())


def _write_stale_delivery_files(job_dir: Path) -> tuple[Path, ...]:
    paths = build_delivery_artifact_paths(job_dir, include_reference=True)
    for path in paths:
        path.write_bytes(b"old")
    for filename in EDITABLE_PPT_FILENAMES.values():
        output_pptx = job_dir / filename
        self_check = build_editable_delivery_cache_path(output_pptx)
        if self_check not in paths:
            raise AssertionError(f"测试漏掉缓存路径：{self_check}")
    return paths


if __name__ == "__main__":
    unittest.main()
