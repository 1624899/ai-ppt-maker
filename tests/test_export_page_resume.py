from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from PIL import Image

from ppt_system.export.export_page_resume import CHECKPOINT_FILE_NAME
from ppt_system.export.export_pipeline import export_project_to_pptx
from ppt_system.export.text_script_runtime import execute_generated_text_script


class FakeChatProvider:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[list[dict[str, Any]]] = []

    def build_image_message_item(self, image_path: Path) -> dict[str, Any]:
        return {"type": "image_url", "image_url": {"url": str(image_path)}}

    def complete_json(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        self.calls.append(messages)
        if not self.responses:
            raise RuntimeError("no more responses")
        return self.responses.pop(0)


def _create_test_image(path: Path, *, alpha: bool) -> None:
    background = (255, 255, 255, 0) if alpha else (255, 255, 255, 255)
    Image.new("RGBA", (400, 240), background).save(path)
    if alpha:
        with Image.open(path).convert("RGBA") as image:
            image.paste((0, 82, 214, 255), (40, 40, 120, 100))
            image.save(path)


def test_export_project_to_pptx_resumes_completed_pages_from_checkpoints() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        work_dir = root / "work"
        output_pptx = root / "result.pptx"
        visual_path_1 = root / "visual_01.png"
        reference_path_1 = root / "reference_01.png"
        visual_path_2 = root / "visual_02.png"
        reference_path_2 = root / "reference_02.png"

        _create_test_image(visual_path_1, alpha=True)
        _create_test_image(reference_path_1, alpha=False)
        _create_test_image(visual_path_2, alpha=True)
        _create_test_image(reference_path_2, alpha=False)

        project = {
            "slide_width_inch": 13.333333,
            "image_width": 400,
            "image_height": 240,
            "default_font": {"font_name": "Microsoft YaHei", "font_size": 24, "color": "355C7D"},
            "pages": [
                {
                    "page_no": 1,
                    "title": "第一页",
                    "summary": "摘要1",
                    "visual_image": str(visual_path_1),
                    "reference_image": str(reference_path_1),
                    "texts": [],
                },
                {
                    "page_no": 2,
                    "title": "第二页",
                    "summary": "摘要2",
                    "visual_image": str(visual_path_2),
                    "reference_image": str(reference_path_2),
                    "texts": [],
                },
            ],
        }
        first_run_provider = FakeChatProvider(
            [
                {"page_script": 'add_text(slide, "第一页成稿", 12, 14, 130, 36, size=20, color="163A63", bold=True)'},
                {"page_script": 'add_text(slide, "第二页成稿", 12, 14, 130, 36, size=20, color="163A63", bold=True)'},
            ]
        )
        second_run_provider = FakeChatProvider(
            [
                {"page_script": 'add_text(slide, "第二页成稿", 12, 14, 130, 36, size=20, color="163A63", bold=True)'},
            ]
        )

        original_execute = execute_generated_text_script
        failing_state = {"triggered": False}

        def fail_after_first_page(
            script_path: Path,
            *,
            timeout_seconds: int = 600,
            stop_checker=None,
        ) -> None:
            if script_path.name == "generated_text_layout_preview_round_01.py":
                original_execute(script_path, timeout_seconds=timeout_seconds, stop_checker=stop_checker)
                if "page_02" in str(script_path):
                    failing_state["triggered"] = True
                    raise RuntimeError("模拟第 2 页导出失败")
                return
            original_execute(script_path, timeout_seconds=timeout_seconds, stop_checker=stop_checker)

        with patch("ppt_system.export.direct_project_script.render_pptx_first_slide_to_png", return_value=None):
            with patch("ppt_system.export.direct_project_script.execute_generated_text_script", side_effect=fail_after_first_page):
                try:
                    export_project_to_pptx(
                        project,
                        work_dir,
                        output_pptx,
                        chat_provider=first_run_provider,  # type: ignore[arg-type]
                    )
                except RuntimeError as exc:
                    assert "模拟第 2 页导出失败" in str(exc)
                else:
                    raise AssertionError("预期第 2 页导出失败，但任务未失败")

        assert failing_state["triggered"] is True
        assert (work_dir / "page_01" / CHECKPOINT_FILE_NAME).exists()
        assert not (work_dir / "page_02" / CHECKPOINT_FILE_NAME).exists()
        assert len(first_run_provider.calls) == 2

        with patch("ppt_system.export.direct_project_script.render_pptx_first_slide_to_png", return_value=None):
            result = export_project_to_pptx(
                project,
                work_dir,
                output_pptx,
                chat_provider=second_run_provider,  # type: ignore[arg-type]
            )

        final_script = Path(result["text_script_path"]).read_text(encoding="utf-8")
        assert output_pptx.exists()
        assert len(second_run_provider.calls) == 1
        assert result["page_count"] == 4
        assert result["logical_page_count"] == 2
        assert "第一页成稿" in final_script
        assert "第二页成稿" in final_script
        assert (work_dir / "page_02" / CHECKPOINT_FILE_NAME).exists()
