from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ppt_system.export.delivery_options import EDITABLE_PPT_FILENAMES, REFERENCE_PPT_FILENAME
from ppt_system.export.editable_delivery_cache import build_editable_delivery_cache_path


@dataclass(frozen=True)
class DeliveryInvalidationSummary:
    removed: tuple[Path, ...] = ()
    failed: tuple[Path, ...] = ()


class DeliveryInvalidationError(RuntimeError):
    def __init__(self, summary: DeliveryInvalidationSummary) -> None:
        self.summary = summary
        failed_names = "、".join(path.name for path in summary.failed)
        super().__init__(f"旧交付文件删除失败，请关闭正在占用的文件后重试：{failed_names}")


def build_empty_delivery_result() -> dict[str, Any]:
    return {
        "deliveries": {},
        "editable_delivery_bundle": {},
    }


def invalidate_delivery_result(state: dict[str, Any]) -> dict[str, Any]:
    state["result"] = build_empty_delivery_result()
    return state["result"]


def invalidate_job_snapshot_result(runtime: Any, job_dir: Path) -> None:
    snapshot = runtime.load_job_snapshot(job_dir)
    if not snapshot:
        return
    snapshot["result"] = build_empty_delivery_result()
    runtime.write_job_snapshot(job_dir, snapshot)


def invalidate_job_record_result(runtime: Any, job_id: str) -> None:
    runtime.update_job_record(runtime.JOBS_DB_PATH, job_id, result=build_empty_delivery_result())


def remove_stale_delivery_files(
    job_dir: Path,
    *,
    include_reference: bool,
    include_editable: bool = True,
) -> DeliveryInvalidationSummary:
    removed: list[Path] = []
    failed: list[Path] = []
    paths = build_delivery_artifact_paths(
        job_dir,
        include_reference=include_reference,
        include_editable=include_editable,
    )
    for path in paths:
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except OSError:
            failed.append(path)
        else:
            removed.append(path)
    return DeliveryInvalidationSummary(removed=tuple(removed), failed=tuple(failed))


def invalidate_delivery_artifacts(
    runtime: Any,
    job_dir: Path,
    *,
    job_id: str | None = None,
    state: dict[str, Any] | None = None,
    include_reference: bool,
    include_editable: bool = True,
) -> DeliveryInvalidationSummary:
    summary = remove_stale_delivery_files(
        job_dir,
        include_reference=include_reference,
        include_editable=include_editable,
    )
    if summary.failed:
        raise DeliveryInvalidationError(summary)

    if state is not None:
        invalidate_delivery_result(state)
    invalidate_job_snapshot_result(runtime, job_dir)
    if job_id:
        invalidate_job_record_result(runtime, job_id)
    return summary


def build_delivery_artifact_paths(
    job_dir: Path,
    *,
    include_reference: bool,
    include_editable: bool = True,
) -> tuple[Path, ...]:
    paths: list[Path] = []
    if include_reference:
        paths.append(job_dir / REFERENCE_PPT_FILENAME)
    if include_editable:
        for filename in EDITABLE_PPT_FILENAMES.values():
            output_pptx = job_dir / filename
            paths.append(output_pptx)
            paths.append(build_editable_delivery_cache_path(output_pptx))
    return tuple(dict.fromkeys(paths))
