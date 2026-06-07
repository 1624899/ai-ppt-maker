from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ppt_system.web.services.job_artifact_paths import resolve_job_artifact_path


class JobArtifactPathTests(unittest.TestCase):
    def test_resolve_job_artifact_path_accepts_run_relative_and_absolute_inside_job_dir(self) -> None:
        with TemporaryDirectory() as temp_dir:
            job_dir = Path(temp_dir) / "job-test"
            image_path = job_dir / "04_image_edits" / "page_01" / "candidate.png"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(b"image")

            self.assertEqual(
                resolve_job_artifact_path(job_dir, "job-test", "/runs/job-test/04_image_edits/page_01/candidate.png"),
                image_path,
            )
            self.assertEqual(
                resolve_job_artifact_path(job_dir, "job-test", "04_image_edits/page_01/candidate.png"),
                image_path,
            )
            self.assertEqual(
                resolve_job_artifact_path(job_dir, "job-test", str(image_path)),
                image_path,
            )

    def test_resolve_job_artifact_path_rejects_paths_outside_job_dir(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            job_dir = root / "job-test"
            job_dir.mkdir(parents=True, exist_ok=True)
            outside_path = root / "outside.png"
            outside_path.write_bytes(b"outside")
            traversal_target = root / "escape.png"
            traversal_target.write_bytes(b"escape")

            self.assertIsNone(resolve_job_artifact_path(job_dir, "job-test", str(outside_path)))
            self.assertIsNone(resolve_job_artifact_path(job_dir, "job-test", "../escape.png"))

    def test_resolve_job_artifact_path_rejects_other_job_run_refs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            job_dir = Path(temp_dir) / "job-test"
            image_path = job_dir / "04_image_edits" / "page_01" / "candidate.png"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(b"image")

            self.assertIsNone(
                resolve_job_artifact_path(job_dir, "job-test", "/runs/other-job/04_image_edits/page_01/candidate.png")
            )
            self.assertIsNone(
                resolve_job_artifact_path(job_dir, "job-test", "runs/other-job/04_image_edits/page_01/candidate.png")
            )

    def test_resolve_job_artifact_path_rejects_missing_or_non_image_artifacts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            job_dir = Path(temp_dir) / "job-test"
            text_path = job_dir / "04_image_edits" / "candidate.txt"
            text_path.parent.mkdir(parents=True, exist_ok=True)
            text_path.write_text("not image", encoding="utf-8")

            self.assertIsNone(resolve_job_artifact_path(job_dir, "job-test", "04_image_edits/candidate.txt"))
            self.assertIsNone(resolve_job_artifact_path(job_dir, "job-test", "04_image_edits/missing.png"))


if __name__ == "__main__":
    unittest.main()
