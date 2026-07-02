from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from PIL import Image

from ppt_system.export.export_page_resume import CHECKPOINT_FILE_NAME
from ppt_system.export.export_step_checkpoint import STEP_CHECKPOINT_DIR_NAME
from ppt_system.export.export_pipeline import export_project_to_pptx
from ppt_system.export.text_script_runtime import execute_generated_text_script
from ppt_system.export.export_asset_checkpoint import ASSET_CHECKPOINT_FILE_NAME


class FakeChatProvider:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[list[dict[str, Any]]] = []
        self.api_base_url = "https://example.com/v1"
        self.model = "fake-chat"
        self.temperature = 0.3
        self.max_tokens = 5000
        self.reasoning_effort = ""

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


def _build_single_page_project(visual_path: Path, reference_path: Path) -> dict[str, Any]:
    return {
        "slide_width_inch": 13.333333,
        "image_width": 400,
        "image_height": 240,
        "default_font": {"font_name": "Microsoft YaHei", "font_size": 24, "color": "355C7D"},
        "pages": [
            {
                "page_no": 1,
                "title": "第一页",
                "summary": "摘要1",
                "visual_image": str(visual_path),
                "reference_image": str(reference_path),
                "texts": [],
            },
        ],
    }


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
        second_run_provider = FakeChatProvider([])

        original_execute = execute_generated_text_script
        failing_state = {"triggered": False}

        def fail_after_first_page(
            script_path: Path,
            *,
            timeout_seconds: int = 180,
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
        assert list((work_dir / "page_02" / STEP_CHECKPOINT_DIR_NAME).glob("initial_script.*.json"))
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
        assert len(second_run_provider.calls) == 0
        assert result["page_count"] == 4
        assert result["logical_page_count"] == 2
        assert "第一页成稿" in final_script
        assert "第二页成稿" in final_script
        assert (work_dir / "page_02" / CHECKPOINT_FILE_NAME).exists()


def test_export_project_to_pptx_skips_asset_prepare_for_completed_page_checkpoint() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        work_dir = root / "work"
        output_pptx = root / "result.pptx"
        visual_path = root / "visual_01.png"
        reference_path = root / "reference_01.png"

        _create_test_image(visual_path, alpha=True)
        _create_test_image(reference_path, alpha=False)
        project = _build_single_page_project(visual_path, reference_path)

        first_run_provider = FakeChatProvider(
            [
                {"page_script": 'add_text(slide, "第一页成稿", 12, 14, 130, 36, size=20, color="163A63", bold=True)'},
            ]
        )
        second_run_provider = FakeChatProvider([])

        with patch("ppt_system.export.direct_project_script.render_pptx_first_slide_to_png", return_value=None):
            export_project_to_pptx(
                project,
                work_dir,
                output_pptx,
                chat_provider=first_run_provider,  # type: ignore[arg-type]
            )

        assert (work_dir / "page_01" / CHECKPOINT_FILE_NAME).exists()

        with patch(
            "ppt_system.export.direct_project_script.prepare_direct_page_assets",
            side_effect=AssertionError("完成页不应重新准备资产"),
        ):
            result = export_project_to_pptx(
                project,
                work_dir,
                output_pptx,
                chat_provider=second_run_provider,  # type: ignore[arg-type]
            )

        assert len(second_run_provider.calls) == 0
        assert result["logical_page_count"] == 1


def test_export_project_to_pptx_reuses_asset_prepare_checkpoint_after_later_failure() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        work_dir = root / "work"
        output_pptx = root / "result.pptx"
        visual_path = root / "visual_01.png"
        reference_path = root / "reference_01.png"

        _create_test_image(visual_path, alpha=True)
        _create_test_image(reference_path, alpha=False)
        project = _build_single_page_project(visual_path, reference_path)

        first_run_provider = FakeChatProvider(
            [
                {"page_script": 'add_text(slide, "首轮文字", 12, 14, 130, 36, size=20, color="163A63", bold=True)'},
            ]
        )
        second_run_provider = FakeChatProvider([])
        failed_after_asset_prepare = {"value": False}

        def fail_after_asset_prepare(*args, **kwargs) -> None:
            failed_after_asset_prepare["value"] = True
            raise RuntimeError("模拟首轮预览脚本执行失败")

        with patch("ppt_system.export.direct_project_script.execute_generated_text_script", side_effect=fail_after_asset_prepare):
            try:
                export_project_to_pptx(
                    project,
                    work_dir,
                    output_pptx,
                    chat_provider=first_run_provider,  # type: ignore[arg-type]
                )
            except RuntimeError as exc:
                assert "模拟首轮预览脚本执行失败" in str(exc)
            else:
                raise AssertionError("预期首轮预览失败，但任务未失败")

        assert failed_after_asset_prepare["value"] is True
        assert (work_dir / "page_01" / ASSET_CHECKPOINT_FILE_NAME).exists()
        assert not (work_dir / "page_01" / CHECKPOINT_FILE_NAME).exists()

        with patch("ppt_system.export.direct_project_script.render_pptx_first_slide_to_png", return_value=None):
            with patch(
                "ppt_system.export.direct_project_script.prepare_direct_page_assets",
                side_effect=AssertionError("资产准备缓存命中后不应重新拟合或切分"),
            ):
                result = export_project_to_pptx(
                    project,
                    work_dir,
                    output_pptx,
                    chat_provider=second_run_provider,  # type: ignore[arg-type]
                )

        assert len(second_run_provider.calls) == 0
        assert (work_dir / "page_01" / CHECKPOINT_FILE_NAME).exists()
        assert result["logical_page_count"] == 1


def test_export_project_to_pptx_reuses_refine_step_checkpoint_after_later_failure() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        work_dir = root / "work"
        output_pptx = root / "result.pptx"
        visual_path = root / "visual_01.png"
        reference_path = root / "reference_01.png"

        _create_test_image(visual_path, alpha=True)
        _create_test_image(reference_path, alpha=False)

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
                    "visual_image": str(visual_path),
                    "reference_image": str(reference_path),
                    "texts": [],
                },
            ],
        }
        first_run_provider = FakeChatProvider(
            [
                {"page_script": 'add_text(slide, "首轮文字", 12, 14, 130, 36, size=20, color="163A63", bold=True)'},
                {"page_script": 'add_text(slide, "修正文字", 16, 18, 140, 40, size=22, color="163A63", bold=True)'},
            ]
        )
        second_run_provider = FakeChatProvider([])
        failed_after_refine = {"value": False}
        rendered_preview_paths: list[Path] = []

        def fail_after_refine_checkpoint(*args, **kwargs) -> dict[str, Any]:
            failed_after_refine["value"] = True
            raise RuntimeError("模拟修正后重叠检查失败")

        def render_same_preview_to_unique_path(
            pptx_path: Path,
            output_path: Path,
            *,
            image_width: int,
            image_height: int,
            stop_checker=None,
        ) -> Path:
            rendered_preview_paths.append(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(reference_path, output_path)
            return output_path

        with patch(
            "ppt_system.export.direct_project_script.render_pptx_first_slide_to_png",
            side_effect=render_same_preview_to_unique_path,
        ):
            with patch(
                "ppt_system.export.direct_project_script.analyze_text_asset_overlaps",
                side_effect=fail_after_refine_checkpoint,
            ):
                try:
                    export_project_to_pptx(
                        project,
                        work_dir,
                        output_pptx,
                        chat_provider=first_run_provider,  # type: ignore[arg-type]
                    )
                except RuntimeError as exc:
                    assert "模拟修正后重叠检查失败" in str(exc)
                else:
                    raise AssertionError("预期修正后失败，但任务未失败")

        assert failed_after_refine["value"] is True
        assert not (work_dir / "page_01" / CHECKPOINT_FILE_NAME).exists()
        assert list((work_dir / "page_01" / STEP_CHECKPOINT_DIR_NAME).glob("initial_script.*.json"))
        assert list((work_dir / "page_01" / STEP_CHECKPOINT_DIR_NAME).glob("refine_round_01.*.json"))
        assert len(first_run_provider.calls) == 2

        with patch(
            "ppt_system.export.direct_project_script.render_pptx_first_slide_to_png",
            side_effect=render_same_preview_to_unique_path,
        ):
            result = export_project_to_pptx(
                project,
                work_dir,
                output_pptx,
                chat_provider=second_run_provider,  # type: ignore[arg-type]
            )

        final_script = Path(result["text_script_path"]).read_text(encoding="utf-8")
        assert len(rendered_preview_paths) == 2
        assert rendered_preview_paths[0] != rendered_preview_paths[1]
        assert len(second_run_provider.calls) == 0
        assert "修正文字" in final_script
        assert (work_dir / "page_01" / CHECKPOINT_FILE_NAME).exists()


def test_preview_pptx_uses_unique_path_after_page_edit() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        work_dir = root / "work"
        output_pptx = root / "result.pptx"
        visual_path = root / "visual_01.png"
        reference_path = root / "reference_01.png"

        _create_test_image(visual_path, alpha=True)
        _create_test_image(reference_path, alpha=False)

        project = _build_single_page_project(visual_path, reference_path)
        edited_project = _build_single_page_project(visual_path, reference_path)
        edited_project["pages"][0]["texts"] = [{"id": "headline", "text": "编辑后的标题"}]
        rendered_pptx_paths: list[Path] = []

        def capture_rendered_input(
            pptx_path: Path,
            output_path: Path,
            *,
            image_width: int,
            image_height: int,
            stop_checker=None,
        ) -> None:
            rendered_pptx_paths.append(Path(pptx_path))
            return None

        first_run_provider = FakeChatProvider(
            [{"page_script": 'add_text(slide, "初版", 12, 14, 130, 36, size=20)'}]
        )
        second_run_provider = FakeChatProvider(
            [{"page_script": 'add_text(slide, "编辑版", 12, 14, 130, 36, size=20)'}]
        )

        with patch("ppt_system.export.direct_project_script.render_pptx_first_slide_to_png", side_effect=capture_rendered_input):
            export_project_to_pptx(
                project,
                work_dir,
                output_pptx,
                chat_provider=first_run_provider,  # type: ignore[arg-type]
            )
            export_project_to_pptx(
                edited_project,
                work_dir,
                output_pptx,
                chat_provider=second_run_provider,  # type: ignore[arg-type]
            )

        assert len(rendered_pptx_paths) == 2
        assert rendered_pptx_paths[0] != rendered_pptx_paths[1]
        assert all(not path.exists() for path in rendered_pptx_paths)
        assert all(path.parent.name == "preview_pptx" for path in rendered_pptx_paths)
        assert all(path.name.startswith("render_preview_round_01_") for path in rendered_pptx_paths)
        assert all(path.suffix == ".pptx" for path in rendered_pptx_paths)
        assert (work_dir / "page_01" / "generated_text_layout_preview_round_01.py").exists()


def test_preview_artifacts_are_cleaned_when_refine_fails() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        work_dir = root / "work"
        output_pptx = root / "result.pptx"
        visual_path = root / "visual_01.png"
        reference_path = root / "reference_01.png"

        _create_test_image(visual_path, alpha=True)
        _create_test_image(reference_path, alpha=False)

        page_dir = work_dir / "page_01"
        old_pptx_paths = [page_dir / "preview_pptx" / f"render_preview_round_01_old_{index}.pptx" for index in range(9)]
        old_image_paths = [page_dir / "preview_images" / f"office_preview_round_01_old_{index}.png" for index in range(9)]
        old_comparison_paths = [
            page_dir / "preview_comparisons" / f"comparison_round_01_old_{index}.png" for index in range(9)
        ]
        for old_path in [*old_pptx_paths, *old_image_paths, *old_comparison_paths]:
            old_path.parent.mkdir(parents=True, exist_ok=True)
            old_path.write_bytes(b"old")

        project = _build_single_page_project(visual_path, reference_path)
        provider = FakeChatProvider(
            [{"page_script": 'add_text(slide, "初版", 12, 14, 130, 36, size=20)'}]
        )
        rendered_preview_paths: list[Path] = []

        def render_preview(
            pptx_path: Path,
            output_path: Path,
            *,
            image_width: int,
            image_height: int,
            stop_checker=None,
        ) -> Path:
            rendered_preview_paths.append(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(reference_path, output_path)
            return output_path

        with patch("ppt_system.export.direct_project_script.render_pptx_first_slide_to_png", side_effect=render_preview):
            with patch(
                "ppt_system.export.direct_project_script._revise_page_script_with_rendered_preview",
                side_effect=RuntimeError("模拟修正失败"),
            ):
                try:
                    export_project_to_pptx(
                        project,
                        work_dir,
                        output_pptx,
                        chat_provider=provider,  # type: ignore[arg-type]
                    )
                except RuntimeError as exc:
                    assert "模拟修正失败" in str(exc)
                else:
                    raise AssertionError("预期修正失败，但任务未失败")

        assert rendered_preview_paths
        assert not any((page_dir / "preview_pptx").glob("render_preview_round_01_*.pptx"))
        assert not any((page_dir / "preview_images").glob("office_preview_round_01_*.png"))
        assert not any((page_dir / "preview_comparisons").glob("comparison_round_01_*.png"))
        assert not any(path.exists() for path in old_pptx_paths)
        assert not any(path.exists() for path in old_image_paths)
        assert not any(path.exists() for path in old_comparison_paths)
