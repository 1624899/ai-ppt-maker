from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image

from ppt_system.asset_pipeline import render_command_template, run_external_stage
from ppt_system.export_pipeline import build_project_from_web_job


class AssetPipelineTests(unittest.TestCase):
    def test_render_command_template_supports_paths_and_page_number(self) -> None:
        command = render_command_template(
            "tool --input {input} --output {output} --page {page_no}",
            input_path=Path("D:/demo/input image.png"),
            output_path=Path("D:/demo/out/output.png"),
            page_no=3,
        )

        self.assertIn("--page 3", command)
        self.assertIn("'D:\\demo\\input image.png'", command)
        self.assertIn("'D:\\demo\\out\\output.png'", command)

    def test_run_external_stage_checks_output_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "input.png"
            output_path = root / "output.png"
            Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(input_path)

            def fake_runner(_command: str, *, timeout_seconds: int) -> None:
                self.assertEqual(timeout_seconds, 15)
                Image.new("RGBA", (8, 8), (0, 255, 0, 255)).save(output_path)

            with patch("ppt_system.asset_pipeline._run_shell_command", side_effect=fake_runner):
                result = run_external_stage(
                    stage_name="enhance",
                    command_template="fake --input {input} --output {output}",
                    input_path=input_path,
                    output_path=output_path,
                    page_no=1,
                    timeout_seconds=15,
                )

            self.assertTrue(output_path.exists())
            self.assertEqual(result.strategy, "external:enhance")

    def test_build_project_from_web_job_keeps_reference_image_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            job_dir = Path(temp_dir)
            reference_dir = job_dir / "01_reference_pages"
            element_dir = job_dir / "02_elements_pages"
            reference_dir.mkdir(parents=True, exist_ok=True)
            element_dir.mkdir(parents=True, exist_ok=True)

            reference_path = reference_dir / "page_01_reference.png"
            element_path = element_dir / "page_01_elements.png"
            Image.new("RGBA", (8, 8), (255, 255, 255, 255)).save(reference_path)
            Image.new("RGBA", (8, 8), (255, 255, 255, 255)).save(element_path)

            project = build_project_from_web_job(
                {
                    "content": "demo",
                    "plan": {"style_guide": {}},
                    "pages": [{"page_no": 1, "title": "封面", "summary": "摘要", "texts": []}],
                    "reference_pages": [{"page_no": 1, "image": "/runs/job-1/01_reference_pages/page_01_reference.png"}],
                    "element_pages": [{"page_no": 1, "image": "/runs/job-1/02_elements_pages/page_01_elements.png"}],
                },
                job_dir,
                title="demo",
                image_width=2048,
                image_height=1152,
            )

            self.assertEqual(project["pages"][0]["reference_image"], str(reference_path))


if __name__ == "__main__":
    unittest.main()
