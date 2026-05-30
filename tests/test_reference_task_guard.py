from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

from main import submit_reference_task


class _DummyImageProvider:
    def generate_reference_page(self, *_args, **_kwargs) -> None:
        raise AssertionError("空 prompt 场景不应触发生图调用")


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


if __name__ == "__main__":
    unittest.main()
