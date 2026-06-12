from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from ppt_system.export.export_artifact_policy import (
    ExportArtifactLockedError,
    build_round_preview_artifacts,
    cleanup_round_preview_artifacts,
    save_final_presentation_atomically,
)
from ppt_system.export.export_step_checkpoint import build_file_content_signature


class FakePresentation:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.saved_paths: list[Path] = []

    def save(self, output_path: Path) -> None:
        path = Path(output_path)
        self.saved_paths.append(path)
        path.write_bytes(self.content)


def test_final_pptx_is_written_to_temp_then_atomically_replaced() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        output_path = root / "result.pptx"
        output_path.write_bytes(b"old")

        presentation = FakePresentation(b"new")

        result = save_final_presentation_atomically(presentation, output_path)

        assert result == output_path
        assert output_path.read_bytes() == b"new"
        assert presentation.saved_paths[0] != output_path
        assert presentation.saved_paths[0].name.startswith(".result.writing_")
        assert not presentation.saved_paths[0].exists()


def test_final_pptx_locked_during_replace_reports_actionable_message() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        output_path = root / "result.pptx"
        output_path.write_bytes(b"old")
        presentation = FakePresentation(b"new")

        with patch("ppt_system.export.export_artifact_policy.os.replace", side_effect=PermissionError(13, "denied")):
            with pytest.raises(ExportArtifactLockedError) as exc_info:
                save_final_presentation_atomically(presentation, output_path)

        message = str(exc_info.value)
        assert "无法更新 PPT 文件" in message
        assert "请关闭该 PPT 文件后重新导出" in message
        assert output_path.read_bytes() == b"old"
        assert not presentation.saved_paths[0].exists()


def test_round_preview_artifacts_are_unique_and_old_files_are_cleaned() -> None:
    with TemporaryDirectory() as temp_dir:
        page_dir = Path(temp_dir) / "page_01"
        artifacts = [build_round_preview_artifacts(page_dir, 1) for _ in range(5)]
        all_paths: list[Path] = []

        for index, item in enumerate(artifacts):
            paths = [item.pptx_path, item.image_path, item.comparison_path]
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(str(index), encoding="utf-8")
                os.utime(path, (index + 1, index + 1))
            all_paths.extend(paths)
        legacy_paths = [
            page_dir / "render_preview_round_01.pptx",
            page_dir / "office_preview_round_01.png",
            page_dir / "office_preview_round_01.PNG",
            page_dir / "comparison_round_01.png",
        ]
        for path in legacy_paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("legacy", encoding="utf-8")
            os.utime(path, (0, 0))

        deleted = cleanup_round_preview_artifacts(
            page_dir,
            1,
            keep=2,
            protect_paths=[
                artifacts[-1].pptx_path,
                artifacts[-1].image_path,
                artifacts[-1].comparison_path,
            ],
        )

        assert len(deleted["pptx"]) == 2
        assert len(deleted["images"]) == 2
        assert len(deleted["comparisons"]) == 2
        assert len(deleted["legacy_pptx"]) == 1
        assert len(deleted["legacy_images"]) == 1
        assert len(deleted["legacy_comparisons"]) == 1
        remaining = [path for path in all_paths if path.exists()]
        assert len(remaining) == 9
        assert artifacts[-1].pptx_path.exists()
        assert artifacts[-1].image_path.exists()
        assert artifacts[-1].comparison_path.exists()
        assert not any(path.exists() for path in legacy_paths)


def test_file_content_signature_can_ignore_unique_intermediate_path() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        first_path = root / "preview_images" / "office_preview_round_01_first.png"
        second_path = root / "preview_images" / "office_preview_round_01_second.png"
        first_path.parent.mkdir(parents=True, exist_ok=True)
        first_path.write_bytes(b"same rendered preview")
        second_path.write_bytes(first_path.read_bytes())

        first_signature = build_file_content_signature(first_path, include_path=False)
        second_signature = build_file_content_signature(second_path, include_path=False)

        assert first_signature == second_signature
        assert "path" not in first_signature
        assert build_file_content_signature(first_path) != build_file_content_signature(second_path)
