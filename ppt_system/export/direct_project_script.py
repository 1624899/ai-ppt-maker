from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ppt_system.image.asset_alignment_runtime import analyze_text_asset_overlaps
from ppt_system.jobs.concurrent_stage import drain_fail_safe_futures
from ppt_system.export.direct_page_script import (
    build_direct_page_preview_project,
    _generate_page_script_from_images,
    prepare_direct_page_assets,
    render_direct_comparison_image,
    resolve_canvas_size,
    _revise_page_script_with_rendered_preview,
    _write_page_preview_script,
)
from ppt_system.export.export_page_resume import (
    build_export_page_signature,
    load_export_page_checkpoint,
    save_export_page_checkpoint,
)
from ppt_system.export.export_step_checkpoint import (
    build_export_step_signature,
    build_file_content_signature,
    load_export_step_checkpoint,
    save_export_step_checkpoint,
    stable_hash_payload,
)
from ppt_system.export.export_layer_mode import SEPARATE_LAYER_MODE
from ppt_system.export.export_asset_checkpoint import (
    build_export_asset_prepare_signature,
    load_export_asset_prepare_checkpoint,
    save_export_asset_prepare_checkpoint,
)
from ppt_system.integrations.openai_chat_provider import OpenAIChatProvider
from ppt_system.export.ppt_calibration_renderer import render_pptx_first_slide_to_png
from ppt_system.export.text_script_runtime import normalize_asset_adjustments, normalize_page_script
from ppt_system.export.text_script_runtime import build_project_script_source, execute_generated_text_script
from ppt_system.image.global_element_alignment import GLOBAL_ELEMENT_ALIGNMENT_VERSION
from ppt_system.image.text_placeholder_detection import load_text_placeholders, placeholder_bboxes, save_text_placeholders


StageLogger = Callable[[str], None]
PageLogger = Callable[[int, str], None]
StopChecker = Callable[[], bool]


@dataclass(frozen=True)
class PreparedProjectPageAssets:
    page_no: int
    assets_manifest: str
    text_placeholders_path: str
    split_source_image: str
    transparent_preview_image: str | None
    asset_count: int
    global_alignment: dict[str, Any] | None
    asset_adjustments: dict[str, Any]
    image_width: int
    image_height: int


def _log(stage_logger: StageLogger | None, message: str) -> None:
    if stage_logger:
        stage_logger(message)


def _log_page(page_logger: PageLogger | None, page_no: int, message: str) -> None:
    if page_logger:
        page_logger(page_no, message)


def _ensure_not_stopped(stop_checker: StopChecker | None) -> None:
    if stop_checker and stop_checker():
        raise InterruptedError("导出流程已被中断")


def _build_asset_option_signature_payload(
    *,
    alpha_threshold: int,
    min_area: int,
    min_width: int,
    min_height: int,
    padding: int,
    merge_distance: int,
    skip_enhance: bool,
    skip_transparent: bool,
) -> dict[str, Any]:
    return {
        "alpha_threshold": int(alpha_threshold),
        "min_area": int(min_area),
        "min_width": int(min_width),
        "min_height": int(min_height),
        "padding": int(padding),
        "merge_distance": int(merge_distance),
        "skip_enhance": bool(skip_enhance),
        "skip_transparent": bool(skip_transparent),
        "global_alignment_version": int(GLOBAL_ELEMENT_ALIGNMENT_VERSION),
    }


def _iter_exportable_project_pages(project: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        page
        for page in sorted(project.get("pages", []), key=lambda item: int(item.get("page_no", 0)))
        if int(page.get("page_no", 0)) > 0
    ]


def _summarize_prepared_page_assets(
    prepared_assets: PreparedProjectPageAssets,
    *,
    source_image: Path,
    merge_distance: int,
) -> dict[str, Any]:
    return {
        "page_no": int(prepared_assets.page_no),
        "asset_count": int(prepared_assets.asset_count),
        "assets_manifest": str(prepared_assets.assets_manifest),
        "text_placeholders": str(prepared_assets.text_placeholders_path),
        "split_source_image": str(prepared_assets.split_source_image),
        "transparent_preview_image": str(prepared_assets.transparent_preview_image or ""),
        "global_alignment": prepared_assets.global_alignment,
        "asset_adjustments": dict(prepared_assets.asset_adjustments),
        "processing": {
            "page_no": int(prepared_assets.page_no),
            "source_image": str(source_image),
            "asset_strategy": "direct_split_elements",
            "merge_distance": int(merge_distance),
            "split_mode": "classic",
        },
    }


def _build_prepared_assets_from_payload(
    payload: dict[str, Any],
    *,
    page_no: int,
    image_width: int,
    image_height: int,
) -> PreparedProjectPageAssets | None:
    manifest_path = Path(str(payload.get("assets_manifest", "")).strip())
    text_placeholders_path = Path(str(payload.get("text_placeholders", "")).strip())
    if not manifest_path.exists() or not text_placeholders_path.exists():
        return None

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(manifest, dict) or int(manifest.get("count", 0)) <= 0:
        return None

    return PreparedProjectPageAssets(
        page_no=int(page_no),
        assets_manifest=str(manifest_path),
        text_placeholders_path=str(text_placeholders_path),
        split_source_image=str(payload.get("split_source_image", "")),
        transparent_preview_image=str(payload.get("transparent_preview_image") or "") or None,
        asset_count=int(manifest.get("count", 0)),
        global_alignment=payload.get("global_alignment") if isinstance(payload.get("global_alignment"), dict) else None,
        asset_adjustments=normalize_asset_adjustments(payload.get("asset_adjustments")),
        image_width=int(image_width),
        image_height=int(image_height),
    )


def _build_prepared_assets_from_completed_page_checkpoint(
    *,
    page_dir: Path,
    page: dict[str, Any],
    page_no: int,
    reference_image: Path,
    visual_image: Path,
    image_width: int,
    image_height: int,
    slide_width_inch: float,
    refine_rounds: int,
    asset_options: dict[str, Any],
) -> PreparedProjectPageAssets | None:
    page_signature = build_export_page_signature(
        page=page,
        page_no=page_no,
        reference_image=reference_image,
        visual_image=visual_image,
        image_width=image_width,
        image_height=image_height,
        slide_width_inch=slide_width_inch,
        refine_rounds=int(refine_rounds),
        asset_options=asset_options,
    )
    checkpoint = load_export_page_checkpoint(page_dir, expected_signature=page_signature)
    if checkpoint is None:
        return None

    payload = dict(checkpoint.page_result)
    payload["asset_adjustments"] = dict(checkpoint.asset_adjustments)
    return _build_prepared_assets_from_payload(
        payload,
        page_no=page_no,
        image_width=image_width,
        image_height=image_height,
    )


def _log_page_alignment_result(
    page_logger: PageLogger | None,
    page_no: int,
    global_alignment: dict[str, Any] | None,
) -> None:
    if not isinstance(global_alignment, dict):
        return
    if bool(global_alignment.get("should_apply")):
        _log_page(
            page_logger,
            page_no,
            f"整页元素拟合对齐已应用：dx={int(global_alignment.get('dx', 0))}, dy={int(global_alignment.get('dy', 0))}",
        )
        return
    _log_page(
        page_logger,
        page_no,
        f"整页元素拟合未应用：{str(global_alignment.get('reason', 'unknown'))}",
    )


def _build_text_asset_overlap_summary(overlap_report: Any) -> dict[str, Any]:
    return {
        "total_boxes": int(overlap_report.total_boxes),
        "overlap_box_count": int(overlap_report.overlap_box_count),
        "overlap_ratio": float(overlap_report.overlap_ratio),
        "max_overlap_pixels": int(overlap_report.max_overlap_pixels),
        "overlapping_box_indices": list(overlap_report.overlapping_box_indices),
    }


def _build_initial_script_step_inputs(
    *,
    reference_image: Path,
    visual_image: Path,
    image_width: int,
    image_height: int,
    text_placeholders: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "reference_image": build_file_content_signature(reference_image),
        "visual_image": build_file_content_signature(visual_image),
        "image_width": int(image_width),
        "image_height": int(image_height),
        "text_placeholders": text_placeholders if isinstance(text_placeholders, dict) else {},
    }


def _load_cached_initial_page_script(
    *,
    page_dir: Path,
    step_signature: dict[str, Any],
) -> str | None:
    checkpoint = load_export_step_checkpoint(page_dir, step_name="initial_script", expected_signature=step_signature)
    if checkpoint is None:
        return None
    try:
        return normalize_page_script(str(checkpoint.payload.get("page_script", "")))
    except RuntimeError:
        return None


def _generate_initial_page_script_with_checkpoint(
    *,
    provider: OpenAIChatProvider,
    page_dir: Path,
    page_signature: dict[str, Any],
    reference_image: Path,
    visual_image: Path,
    image_width: int,
    image_height: int,
    text_placeholders: dict[str, Any] | None,
    page_logger: PageLogger | None,
    page_no: int,
    stop_checker: StopChecker | None = None,
) -> str:
    step_inputs = _build_initial_script_step_inputs(
        reference_image=reference_image,
        visual_image=visual_image,
        image_width=image_width,
        image_height=image_height,
        text_placeholders=text_placeholders,
    )
    step_signature = build_export_step_signature(
        step_name="initial_script",
        operation="direct_page_initial_script",
        page_signature=page_signature,
        provider=provider,
        inputs=step_inputs,
    )
    cached_script = _load_cached_initial_page_script(page_dir=page_dir, step_signature=step_signature)
    if cached_script is not None:
        _log_page(page_logger, page_no, "命中首轮文字脚本子步骤缓存")
        return cached_script

    current_script = _generate_page_script_from_images(
        provider,
        reference_image=reference_image,
        elements_image=visual_image,
        image_width=image_width,
        image_height=image_height,
        text_placeholders=text_placeholders,
        stop_checker=stop_checker,
    )
    save_export_step_checkpoint(
        page_dir,
        step_name="initial_script",
        signature=step_signature,
        payload={"page_script": current_script},
    )
    return current_script


def _build_refine_script_step_inputs(
    *,
    reference_image: Path,
    rendered_preview: Path,
    image_width: int,
    image_height: int,
    page_script: str,
    asset_adjustments: dict[str, Any],
    round_index: int,
) -> dict[str, Any]:
    return {
        "reference_image": build_file_content_signature(reference_image),
        "rendered_preview": build_file_content_signature(rendered_preview),
        "image_width": int(image_width),
        "image_height": int(image_height),
        "page_script_hash": _stable_script_hash(page_script),
        "asset_adjustments": normalize_asset_adjustments(asset_adjustments),
        "round_index": int(round_index),
    }


def _load_cached_refine_page_script(
    *,
    page_dir: Path,
    step_name: str,
    step_signature: dict[str, Any],
    fallback_asset_adjustments: dict[str, Any],
) -> tuple[str, dict[str, Any]] | None:
    checkpoint = load_export_step_checkpoint(page_dir, step_name=step_name, expected_signature=step_signature)
    if checkpoint is None:
        return None
    try:
        page_script = normalize_page_script(str(checkpoint.payload.get("page_script", "")))
    except RuntimeError:
        return None
    raw_adjustments = checkpoint.payload.get("asset_adjustments", fallback_asset_adjustments)
    return page_script, normalize_asset_adjustments(raw_adjustments)


def _revise_page_script_with_checkpoint(
    *,
    provider: OpenAIChatProvider,
    page_dir: Path,
    page_signature: dict[str, Any],
    reference_image: Path,
    rendered_preview: Path,
    image_width: int,
    image_height: int,
    page_script: str,
    asset_adjustments: dict[str, Any],
    round_index: int,
    page_logger: PageLogger | None,
    page_no: int,
    stop_checker: StopChecker | None = None,
) -> tuple[str, dict[str, Any]]:
    step_name = f"refine_round_{int(round_index) + 1:02d}"
    step_inputs = _build_refine_script_step_inputs(
        reference_image=reference_image,
        rendered_preview=rendered_preview,
        image_width=image_width,
        image_height=image_height,
        page_script=page_script,
        asset_adjustments=asset_adjustments,
        round_index=round_index,
    )
    step_signature = build_export_step_signature(
        step_name=step_name,
        operation="direct_page_refine_script",
        page_signature=page_signature,
        provider=provider,
        inputs=step_inputs,
    )
    cached = _load_cached_refine_page_script(
        page_dir=page_dir,
        step_name=step_name,
        step_signature=step_signature,
        fallback_asset_adjustments=asset_adjustments,
    )
    if cached is not None:
        _log_page(page_logger, page_no, f"命中第 {int(round_index) + 1} 轮回看修正子步骤缓存")
        return cached

    refine_result = _revise_page_script_with_rendered_preview(
        provider,
        reference_image=reference_image,
        rendered_preview=rendered_preview,
        image_width=image_width,
        image_height=image_height,
        page_script=page_script,
        asset_adjustments=asset_adjustments,
        round_index=round_index,
        stop_checker=stop_checker,
    )
    payload = {
        "page_script": refine_result.page_script,
        "asset_adjustments": refine_result.asset_adjustments,
    }
    save_export_step_checkpoint(page_dir, step_name=step_name, signature=step_signature, payload=payload)
    return refine_result.page_script, refine_result.asset_adjustments


def _stable_script_hash(page_script: str) -> str:
    return stable_hash_payload(str(page_script))


def prepare_direct_project_assets(
    project: dict[str, Any],
    work_dir: Path,
    *,
    alpha_threshold: int = 8,
    min_area: int = 8,
    min_width: int = 0,
    min_height: int = 0,
    padding: int = 0,
    merge_distance: int = 6,
    skip_enhance: bool = False,
    skip_transparent: bool = False,
    refine_rounds: int = 1,
    stage_logger: StageLogger | None = None,
    page_logger: PageLogger | None = None,
    stop_checker: StopChecker | None = None,
) -> dict[str, Any]:
    """为新主路径准备分割后的元素资产。"""
    work_dir.mkdir(parents=True, exist_ok=True)
    page_summaries: list[dict[str, Any]] = []
    prepared_assets_by_page: dict[int, PreparedProjectPageAssets] = {}
    asset_option_signature_payload = _build_asset_option_signature_payload(
        alpha_threshold=alpha_threshold,
        min_area=min_area,
        min_width=min_width,
        min_height=min_height,
        padding=padding,
        merge_distance=merge_distance,
        skip_enhance=skip_enhance,
        skip_transparent=skip_transparent,
    )
    slide_width_inch = float(project.get("slide_width_inch", 13.333333))
    for page in _iter_exportable_project_pages(project):
        _ensure_not_stopped(stop_checker)
        page_no = int(page.get("page_no", 0))
        visual_image = Path(str(page.get("visual_image", "")))
        reference_image = Path(str(page.get("reference_image", "")))
        if not visual_image.exists():
            raise FileNotFoundError(f"第 {page_no} 页元素图不存在：{visual_image}")
        if not reference_image.exists():
            raise FileNotFoundError(f"第 {page_no} 页原稿图不存在：{reference_image}")

        image_width, image_height = resolve_canvas_size(reference_image, visual_image)
        page_dir = work_dir / f"page_{page_no:02d}"
        text_placeholders_path = page_dir / "text_placeholders.json"
        completed_prepared_assets = _build_prepared_assets_from_completed_page_checkpoint(
            page_dir=page_dir,
            page=page,
            page_no=page_no,
            reference_image=reference_image,
            visual_image=visual_image,
            image_width=image_width,
            image_height=image_height,
            slide_width_inch=slide_width_inch,
            refine_rounds=refine_rounds,
            asset_options=asset_option_signature_payload,
        )
        if completed_prepared_assets is not None:
            prepared_assets_by_page[page_no] = completed_prepared_assets
            _log_page(page_logger, page_no, "检测到已完成页级导出结果，复用已保存元素资产")
            page_summaries.append(
                _summarize_prepared_page_assets(
                    completed_prepared_assets,
                    source_image=visual_image,
                    merge_distance=merge_distance,
                )
            )
            continue

        text_placeholders = save_text_placeholders(
            reference_image,
            visual_image,
            text_placeholders_path,
            slide_width_inch=slide_width_inch,
        )
        asset_signature = build_export_asset_prepare_signature(
            page_no=page_no,
            reference_image=reference_image,
            visual_image=visual_image,
            image_width=image_width,
            image_height=image_height,
            slide_width_inch=slide_width_inch,
            text_placeholders=text_placeholders,
            asset_options=asset_option_signature_payload,
        )
        cached_asset = load_export_asset_prepare_checkpoint(page_dir, expected_signature=asset_signature)
        cached_prepared_assets = (
            _build_prepared_assets_from_payload(
                cached_asset.payload,
                page_no=page_no,
                image_width=image_width,
                image_height=image_height,
            )
            if cached_asset is not None
            else None
        )
        if cached_prepared_assets is not None:
            prepared_assets_by_page[page_no] = cached_prepared_assets
            _log_page(page_logger, page_no, "命中元素资产准备缓存，跳过整页拟合与切分")
            page_summaries.append(
                _summarize_prepared_page_assets(
                    cached_prepared_assets,
                    source_image=visual_image,
                    merge_distance=merge_distance,
                )
            )
            continue

        asset_result = prepare_direct_page_assets(
            work_dir=work_dir,
            page_no=page_no,
            elements_image=visual_image,
            reference_image=reference_image,
            reference_text_boxes=placeholder_bboxes(text_placeholders),
            image_width=image_width,
            image_height=image_height,
            alpha_threshold=alpha_threshold,
            min_area=min_area,
            min_width=min_width,
            min_height=min_height,
            padding=padding,
            merge_distance=merge_distance,
            skip_enhance=skip_enhance,
            skip_transparent=skip_transparent,
            stop_checker=stop_checker,
        )
        manifest = dict(asset_result.manifest)
        prepared_record = PreparedProjectPageAssets(
            page_no=page_no,
            assets_manifest=str(asset_result.manifest_path),
            text_placeholders_path=str(text_placeholders_path),
            split_source_image=str(asset_result.split_source_image),
            transparent_preview_image=asset_result.transparent_preview_image,
            asset_count=int(manifest.get("count", 0)),
            global_alignment=asset_result.global_alignment if isinstance(asset_result.global_alignment, dict) else None,
            asset_adjustments=dict(asset_result.asset_adjustments),
            image_width=int(image_width),
            image_height=int(image_height),
        )
        save_export_asset_prepare_checkpoint(
            page_dir,
            signature=asset_signature,
            payload=_summarize_prepared_page_assets(
                prepared_record,
                source_image=visual_image,
                merge_distance=merge_distance,
            ),
        )
        prepared_assets_by_page[page_no] = prepared_record
        _log_page(page_logger, page_no, f"已准备分割元素资产，共 {int(prepared_record.asset_count)} 个元素")
        _log_page_alignment_result(page_logger, page_no, prepared_record.global_alignment)
        page_summaries.append(
            _summarize_prepared_page_assets(
                prepared_record,
                source_image=visual_image,
                merge_distance=merge_distance,
            )
        )
    _log(stage_logger, f"分割元素资产准备完成，共 {len(page_summaries)} 页")
    return {
        "page_count": len(page_summaries),
        "pages": page_summaries,
        "prepared_assets_by_page": prepared_assets_by_page,
    }


def _generate_direct_project_page_script(
    *,
    provider: OpenAIChatProvider,
    project: dict[str, Any],
    page: dict[str, Any],
    work_dir: Path,
    refine_rounds: int,
    asset_option_signature_payload: dict[str, Any],
    prepared_page_assets: PreparedProjectPageAssets,
    page_logger: PageLogger | None = None,
    stop_checker: StopChecker | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _ensure_not_stopped(stop_checker)
    page_no = int(page.get("page_no", 0))
    if page_no <= 0:
        raise ValueError("页面编号必须大于 0")

    reference_image = Path(str(page.get("reference_image", "")))
    visual_image = Path(str(page.get("visual_image", "")))
    if not reference_image.exists():
        raise FileNotFoundError(f"第 {page_no} 页原稿图不存在：{reference_image}")
    if not visual_image.exists():
        raise FileNotFoundError(f"第 {page_no} 页元素图不存在：{visual_image}")

    page_dir = work_dir / f"page_{page_no:02d}"
    image_width = int(prepared_page_assets.image_width)
    image_height = int(prepared_page_assets.image_height)
    page_signature = build_export_page_signature(
        page=page,
        page_no=page_no,
        reference_image=reference_image,
        visual_image=visual_image,
        image_width=image_width,
        image_height=image_height,
        slide_width_inch=float(project.get("slide_width_inch", 13.333333)),
        refine_rounds=int(refine_rounds),
        asset_options=asset_option_signature_payload,
    )
    checkpoint = load_export_page_checkpoint(page_dir, expected_signature=page_signature)
    if checkpoint is not None:
        _log_page(page_logger, page_no, "检测到已完成页级导出结果，继续从已保存进度执行")
        return (
            {
                "page_no": page_no,
                "script": checkpoint.page_script,
                "asset_adjustments": dict(checkpoint.asset_adjustments),
            },
            dict(checkpoint.page_result),
        )

    preview_project = build_direct_page_preview_project(
        reference_image=reference_image,
        elements_image=visual_image,
        image_width=image_width,
        image_height=image_height,
        slide_width_inch=float(project.get("slide_width_inch", 13.333333)),
        page_no=page_no,
    )
    text_placeholders = load_text_placeholders(Path(prepared_page_assets.text_placeholders_path))
    if text_placeholders is None:
        text_placeholders = save_text_placeholders(
            reference_image,
            visual_image,
            Path(prepared_page_assets.text_placeholders_path),
            slide_width_inch=float(project.get("slide_width_inch", 13.333333)),
        )
    current_asset_adjustments: dict[str, Any] = dict(prepared_page_assets.asset_adjustments)
    preview_project["asset_adjustments"] = {str(page_no): dict(current_asset_adjustments)}
    _log_page(page_logger, page_no, "开始直出首轮文字脚本")
    request_started_at = time.perf_counter()
    current_script = _generate_initial_page_script_with_checkpoint(
        provider=provider,
        page_dir=page_dir,
        page_signature=page_signature,
        reference_image=reference_image,
        visual_image=visual_image,
        image_width=image_width,
        image_height=image_height,
        text_placeholders=text_placeholders,
        page_logger=page_logger,
        page_no=page_no,
        stop_checker=stop_checker,
    )
    _ensure_not_stopped(stop_checker)
    _log_page(page_logger, page_no, f"首轮文字脚本生成完成，耗时 {time.perf_counter() - request_started_at:.1f}s")

    page_result = {
        "page_no": page_no,
        "office_render_available": False,
        "refine_rounds_applied": 0,
        "office_preview_paths": [],
        "comparison_paths": [],
        "text_placeholders": str(prepared_page_assets.text_placeholders_path),
        "assets_manifest": str(prepared_page_assets.assets_manifest),
        "asset_adjustments": dict(current_asset_adjustments),
    }

    for round_index in range(max(0, int(refine_rounds))):
        _ensure_not_stopped(stop_checker)
        preview_pptx = page_dir / f"render_preview_round_{round_index + 1:02d}.pptx"
        preview_script_path = page_dir / f"generated_text_layout_preview_round_{round_index + 1:02d}.py"
        _write_page_preview_script(
            project=preview_project,
            work_dir=work_dir,
            output_pptx=preview_pptx,
            page_no=page_no,
            page_script=current_script,
            script_path=preview_script_path,
        )
        preview_script_started_at = time.perf_counter()
        execute_generated_text_script(preview_script_path, stop_checker=stop_checker)
        _ensure_not_stopped(stop_checker)
        _log_page(page_logger, page_no, f"预览 PPT 脚本执行完成，耗时 {time.perf_counter() - preview_script_started_at:.1f}s")

        preview_image_path = page_dir / f"office_preview_round_{round_index + 1:02d}.png"
        render_started_at = time.perf_counter()
        rendered_preview = render_pptx_first_slide_to_png(
            preview_pptx,
            preview_image_path,
            image_width=image_width,
            image_height=image_height,
            stop_checker=stop_checker,
        )
        _ensure_not_stopped(stop_checker)
        _log_page(page_logger, page_no, f"Office 预览渲染结束，耗时 {time.perf_counter() - render_started_at:.1f}s")
        if rendered_preview is None:
            _log_page(page_logger, page_no, "Office 真渲染不可用，跳过真实导出回看")
            break

        page_result["office_render_available"] = True
        page_result["office_preview_paths"].append(str(rendered_preview))
        comparison_path = page_dir / f"comparison_round_{round_index + 1:02d}.png"
        render_direct_comparison_image(
            reference_image=reference_image,
            preview_image=rendered_preview,
            output_path=comparison_path,
        )
        page_result["comparison_paths"].append(str(comparison_path))
        _log_page(page_logger, page_no, f"开始第 {round_index + 1} 轮真实导出回看修正")
        refine_started_at = time.perf_counter()
        candidate_script, candidate_adjustments = _revise_page_script_with_checkpoint(
            provider=provider,
            page_dir=page_dir,
            page_signature=page_signature,
            reference_image=reference_image,
            rendered_preview=rendered_preview,
            image_width=image_width,
            image_height=image_height,
            page_script=current_script,
            asset_adjustments=current_asset_adjustments,
            round_index=round_index,
            page_logger=page_logger,
            page_no=page_no,
            stop_checker=stop_checker,
        )
        _ensure_not_stopped(stop_checker)
        _log_page(page_logger, page_no, f"第 {round_index + 1} 轮回看修正完成，耗时 {time.perf_counter() - refine_started_at:.1f}s")
        if candidate_script == current_script and candidate_adjustments == current_asset_adjustments:
            _log_page(page_logger, page_no, "修正轮未返回更优脚本，保留当前结果")
            break
        current_script = candidate_script
        current_asset_adjustments = candidate_adjustments
        preview_project["asset_adjustments"] = {str(page_no): dict(current_asset_adjustments)}
        page_result["refine_rounds_applied"] = int(page_result["refine_rounds_applied"]) + 1
        page_result["asset_adjustments"] = dict(current_asset_adjustments)

    page_script = {
        "page_no": page_no,
        "script": current_script,
        "asset_adjustments": dict(current_asset_adjustments),
    }
    if page_result["office_preview_paths"]:
        overlap_report = analyze_text_asset_overlaps(
            manifest_path=Path(prepared_page_assets.assets_manifest),
            page_script=current_script,
            current_adjustments=current_asset_adjustments,
        )
        page_result["text_asset_overlap"] = _build_text_asset_overlap_summary(overlap_report)
    save_export_page_checkpoint(
        page_dir,
        signature=page_signature,
        page_no=page_no,
        page_script=page_script["script"],
        asset_adjustments=page_script.get("asset_adjustments", {}),
        page_result=page_result,
    )
    return page_script, page_result


def generate_direct_project_text_script(
    provider: OpenAIChatProvider,
    project: dict[str, Any],
    work_dir: Path,
    output_pptx: Path,
    *,
    refine_rounds: int = 1,
    alpha_threshold: int = 8,
    min_area: int = 8,
    min_width: int = 0,
    min_height: int = 0,
    padding: int = 0,
    merge_distance: int = 6,
    skip_enhance: bool = False,
    skip_transparent: bool = False,
    page_concurrency: int = 1,
    stage_logger: StageLogger | None = None,
    page_logger: PageLogger | None = None,
    stop_checker: StopChecker | None = None,
) -> dict[str, Any]:
    """按页执行原稿图+元素图首轮和真实导出回看修正，生成整套项目脚本。"""
    assets_summary = prepare_direct_project_assets(
        project,
        work_dir,
        alpha_threshold=alpha_threshold,
        min_area=min_area,
        min_width=min_width,
        min_height=min_height,
        padding=padding,
        merge_distance=merge_distance,
        skip_enhance=skip_enhance,
        skip_transparent=skip_transparent,
        refine_rounds=refine_rounds,
        stage_logger=stage_logger,
        page_logger=page_logger,
        stop_checker=stop_checker,
    )
    prepared_assets_by_page = dict(assets_summary.pop("prepared_assets_by_page", {}))
    page_scripts: list[dict[str, Any]] = []
    page_results: list[dict[str, Any]] = []
    asset_option_signature_payload = _build_asset_option_signature_payload(
        alpha_threshold=alpha_threshold,
        min_area=min_area,
        min_width=min_width,
        min_height=min_height,
        padding=padding,
        merge_distance=merge_distance,
        skip_enhance=skip_enhance,
        skip_transparent=skip_transparent,
    )
    pages = _iter_exportable_project_pages(project)
    concurrency = max(1, int(page_concurrency))
    _log(stage_logger, f"页级导出并发数：{concurrency}")

    def run_single_page(page: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        page_no = int(page.get("page_no", 0))
        prepared_page_assets = prepared_assets_by_page.get(page_no)
        if prepared_page_assets is None:
            raise RuntimeError(f"缺少第 {page_no} 页的已准备资产结果，无法继续生成脚本。")
        return _generate_direct_project_page_script(
            provider=provider,
            project=project,
            page=page,
            work_dir=work_dir,
            refine_rounds=refine_rounds,
            asset_option_signature_payload=asset_option_signature_payload,
            prepared_page_assets=prepared_page_assets,
            page_logger=page_logger,
            stop_checker=stop_checker,
        )

    if concurrency <= 1:
        for page in pages:
            _ensure_not_stopped(stop_checker)
            page_script, page_result = run_single_page(page)
            page_scripts.append(page_script)
            page_results.append(page_result)
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            pending_pages = list(pages)
            futures: dict[Any, dict[str, Any]] = {}

            def refill_page_tasks() -> None:
                _ensure_not_stopped(stop_checker)
                while pending_pages and len(futures) < concurrency:
                    page = pending_pages.pop(0)
                    futures[executor.submit(run_single_page, page)] = page

            def on_page_success(page: dict[str, Any], result: tuple[dict[str, Any], dict[str, Any]]) -> None:
                page_script, page_result = result
                page_scripts.append(page_script)
                page_results.append(page_result)

            def on_page_error(page: dict[str, Any], exc: BaseException) -> None:
                page_no = int(page.get("page_no", 0))
                _log_page(page_logger, page_no, f"页级导出失败：{exc}")

            refill_page_tasks()
            first_error = drain_fail_safe_futures(
                futures,
                refill=refill_page_tasks,
                on_success=on_page_success,
                on_error=on_page_error,
            )
        if first_error is not None:
            raise first_error

    page_scripts.sort(key=lambda item: int(item.get("page_no", 0)))
    page_results.sort(key=lambda item: int(item.get("page_no", 0)))

    script_path = work_dir / "generated_text_layout.py"
    _ensure_not_stopped(stop_checker)
    script_source = build_project_script_source(
        project,
        work_dir,
        output_pptx,
        page_scripts,
        include_assets=True,
        layer_mode=SEPARATE_LAYER_MODE,
    )
    script_path.write_text(script_source, encoding="utf-8")
    return {
        "script_path": str(script_path),
        "assets": assets_summary,
        "pages": page_results,
        "page_scripts": page_scripts,
    }
