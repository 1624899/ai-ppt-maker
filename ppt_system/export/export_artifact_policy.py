from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


FINAL_PPTX_ARTIFACT_KIND = "final_pptx"
PREVIEW_PPTX_ARTIFACT_KIND = "preview_pptx"
DEFAULT_PREVIEW_ARTIFACT_RETENTION = 8


@dataclass(frozen=True)
class RoundPreviewArtifacts:
    script_path: Path
    pptx_path: Path
    image_path: Path
    comparison_path: Path


class ExportArtifactWriteError(RuntimeError):
    def __init__(self, user_message: str, *, artifact_path: Path | None = None) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.artifact_path = artifact_path


class ExportArtifactLockedError(ExportArtifactWriteError):
    pass


def build_round_preview_artifacts(page_dir: Path, round_number: int) -> RoundPreviewArtifacts:
    """生成单轮真实渲染回看的中间产物路径。"""
    resolved_round = int(round_number)
    if resolved_round <= 0:
        raise ValueError("预览轮次必须大于 0。")

    round_stem = f"round_{resolved_round:02d}"
    token = build_unique_artifact_token()
    return RoundPreviewArtifacts(
        script_path=page_dir / f"generated_text_layout_preview_{round_stem}.py",
        pptx_path=page_dir / "preview_pptx" / f"render_preview_{round_stem}_{token}.pptx",
        image_path=page_dir / "preview_images" / f"office_preview_{round_stem}_{token}.png",
        comparison_path=page_dir / "preview_comparisons" / f"comparison_{round_stem}_{token}.png",
    )


def build_unique_artifact_token() -> str:
    token = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"{token}_{os.getpid()}_{uuid.uuid4().hex[:10]}"


def cleanup_round_preview_artifacts(
    page_dir: Path,
    round_number: int,
    *,
    keep: int = DEFAULT_PREVIEW_ARTIFACT_RETENTION,
    protect_paths: Iterable[Path] = (),
) -> dict[str, list[Path]]:
    """清理单轮预览的旧中间产物，避免编辑重跑后工作目录持续膨胀。"""
    resolved_round = int(round_number)
    if resolved_round <= 0:
        raise ValueError("预览轮次必须大于 0。")

    round_stem = f"round_{resolved_round:02d}"
    protected = _normalize_protected_paths(protect_paths)
    return {
        "pptx": cleanup_old_artifacts(
            page_dir / "preview_pptx",
            pattern=f"render_preview_{round_stem}_*.pptx",
            keep=keep,
            protect_paths=protected,
        ),
        "images": cleanup_old_artifacts(
            page_dir / "preview_images",
            pattern=f"office_preview_{round_stem}_*.png",
            keep=keep,
            protect_paths=protected,
        ),
        "comparisons": cleanup_old_artifacts(
            page_dir / "preview_comparisons",
            pattern=f"comparison_{round_stem}_*.png",
            keep=keep,
            protect_paths=protected,
        ),
        "legacy_pptx": cleanup_old_artifacts(
            page_dir,
            pattern=f"render_preview_{round_stem}.pptx",
            keep=0,
            protect_paths=protected,
        ),
        "legacy_images": cleanup_old_artifacts(
            page_dir,
            pattern=f"office_preview_{round_stem}.png",
            keep=0,
            protect_paths=protected,
        ),
        "legacy_comparisons": cleanup_old_artifacts(
            page_dir,
            pattern=f"comparison_{round_stem}.png",
            keep=0,
            protect_paths=protected,
        ),
    }


def cleanup_old_artifacts(
    directory: Path,
    *,
    pattern: str,
    keep: int,
    protect_paths: Iterable[Path] = (),
) -> list[Path]:
    if keep < 0:
        raise ValueError("保留数量不能小于 0。")
    if not directory.exists():
        return []

    protected = _normalize_protected_paths(protect_paths)
    candidates = []
    for path in directory.glob(pattern):
        if not path.is_file() or _resolve_for_compare(path) in protected:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        candidates.append((stat.st_mtime_ns, path.name, path))

    candidates.sort(reverse=True)
    deleted: list[Path] = []
    for _, _, path in candidates[int(keep) :]:
        try:
            path.unlink()
        except OSError:
            continue
        deleted.append(path)
    return deleted


def save_presentation_artifact(
    presentation: Any,
    output_path: Path,
    *,
    kind: str = FINAL_PPTX_ARTIFACT_KIND,
) -> Path:
    resolved_kind = _normalize_artifact_kind(kind)
    target_path = Path(output_path)
    if resolved_kind == PREVIEW_PPTX_ARTIFACT_KIND:
        return save_unique_intermediate_presentation(presentation, target_path)
    return save_final_presentation_atomically(presentation, target_path)


def save_unique_intermediate_presentation(presentation: Any, output_path: Path) -> Path:
    target_path = Path(output_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        presentation.save(target_path)
    except PermissionError as exc:
        raise ExportArtifactWriteError(
            _build_intermediate_permission_message(target_path),
            artifact_path=target_path,
        ) from exc
    return target_path


def save_final_presentation_atomically(presentation: Any, output_path: Path) -> Path:
    target_path = Path(output_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    cleanup_stale_atomic_temp_files(target_path)
    temp_path = build_atomic_temp_path(target_path)
    try:
        presentation.save(temp_path)
    except PermissionError as exc:
        _remove_file_best_effort(temp_path)
        raise ExportArtifactWriteError(
            _build_temp_permission_message(temp_path),
            artifact_path=temp_path,
        ) from exc

    try:
        os.replace(temp_path, target_path)
    except PermissionError as exc:
        _remove_file_best_effort(temp_path)
        raise ExportArtifactLockedError(
            _build_final_locked_message(target_path),
            artifact_path=target_path,
        ) from exc
    except OSError:
        _remove_file_best_effort(temp_path)
        raise
    return target_path


def build_atomic_temp_path(target_path: Path) -> Path:
    token = build_unique_artifact_token()
    return target_path.parent / f".{target_path.stem}.writing_{token}{target_path.suffix}"


def cleanup_stale_atomic_temp_files(output_path: Path, *, keep: int = 2) -> list[Path]:
    target_path = Path(output_path)
    return cleanup_old_artifacts(
        target_path.parent,
        pattern=f".{target_path.stem}.writing_*{target_path.suffix}",
        keep=keep,
    )


def _normalize_artifact_kind(kind: str) -> str:
    value = str(kind or FINAL_PPTX_ARTIFACT_KIND).strip()
    if value == PREVIEW_PPTX_ARTIFACT_KIND:
        return value
    return FINAL_PPTX_ARTIFACT_KIND


def _normalize_protected_paths(paths: Iterable[Path]) -> set[Path]:
    return {_resolve_for_compare(Path(path)) for path in paths if path}


def _resolve_for_compare(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


def _remove_file_best_effort(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _build_final_locked_message(target_path: Path) -> str:
    return (
        f"无法更新 PPT 文件：{target_path}\n"
        "目标文件可能正在 PowerPoint、WPS 或预览窗口中打开。请关闭该 PPT 文件后重新导出。"
    )


def _build_temp_permission_message(temp_path: Path) -> str:
    return (
        f"无法写入导出临时文件：{temp_path}\n"
        "请检查输出目录权限、磁盘同步软件或安全软件是否阻止写入，然后重新导出。"
    )


def _build_intermediate_permission_message(target_path: Path) -> str:
    return (
        f"无法写入预览中间文件：{target_path}\n"
        "请检查工作目录权限，或关闭正在占用该文件的预览程序后重试。"
    )
