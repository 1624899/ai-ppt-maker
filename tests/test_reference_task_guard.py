from __future__ import annotations

import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

from main import submit_elements_task, submit_reference_task


class _DummyImageProvider:
    def generate_reference_page(self, *_args, **_kwargs) -> None:
        raise AssertionError("空 prompt 场景不应触发生图调用")


class _CapturingImageProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Path, Path]] = []

    def generate_elements_page(self, prompt: str, reference_page_path: Path, output_path: Path) -> dict[str, object]:
        self.calls.append((prompt, reference_page_path, output_path))
        output_path.write_bytes(b"elements")
        return {"provider": "fake"}


class ReferenceTaskGuardTests(unittest.TestCase):
    def test_submit_reference_task_rejects_empty_prompt_before_writing_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            stage1_dir = Path(temp_dir)
            job_dir = stage1_dir.parent
            page = {"page_no": 1, "image_prompt": "   "}

            with ThreadPoolExecutor(max_workers=1) as executor:
                with self.assertRaisesRegex(ValueError, "缺少原稿图提示词"):
                    submit_reference_task(
                        executor,
                        job_dir,
                        "job-test",
                        page,
                        stage1_dir,
                        _DummyImageProvider(),
                        [],
                    )

            self.assertFalse((stage1_dir / "page_01_reference_prompt.txt").exists())

    def test_submit_elements_task_uses_explicit_reference_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            job_dir = Path(temp_dir)
            reference_path = job_dir / "04_image_edits" / "page_02" / "candidate_reference.png"
            stage2_dir = job_dir / "02_elements_pages"
            reference_path.parent.mkdir(parents=True, exist_ok=True)
            stage2_dir.mkdir(parents=True, exist_ok=True)
            reference_path.write_bytes(b"current-reference")
            (job_dir / "status.json").write_text(
                json.dumps(
                    {
                        "job_id": "job-test",
                        "status": "running",
                        "current_stage": "elements_generation",
                        "pages": [{"page_no": 2, "status": "reference_done"}],
                        "stages": [{"key": "elements_generation", "logs": []}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            provider = _CapturingImageProvider()

            with ThreadPoolExecutor(max_workers=1) as executor:
                future, page_no, output_path = submit_elements_task(
                    executor,
                    job_dir,
                    "job-test",
                    2,
                    "元素图提示词",
                    reference_path,
                    stage2_dir,
                    provider,
                )
                future.result(timeout=5)

            self.assertEqual(page_no, 2)
            self.assertEqual(output_path, stage2_dir / "page_02_elements.png")
            self.assertEqual(provider.calls[0][1], reference_path)


if __name__ == "__main__":
    unittest.main()
