from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from ppt_system.asset_alignment_runtime import analyze_global_asset_alignment, analyze_text_asset_overlaps
from ppt_system.direct_page_script import (
    _refine_direct_page_script,
    _request_direct_page_script,
    _write_direct_page_script,
    build_direct_single_page_project,
    prepare_direct_page_assets,
    render_direct_comparison_image,
    resolve_canvas_size,
)
from ppt_system.openai_chat_provider import OpenAIChatProvider
from ppt_system.ppt_calibration_renderer import render_pptx_first_slide_to_png
from ppt_system.text_script_runtime import build_project_script_source, execute_generated_text_script


StageLogger = Callable[[str], None]
PageLogger = Callable[[int, str], None]
StopChecker = Callable[[], bool]


def _log(stage_logger: StageLogger | None, message: str) -> None:
    if stage_logger:
        stage_logger(message)


def _log_page(page_logger: PageLogger | None, page_no: int, message: str) -> None:
    if page_logger:
        page_logger(page_no, message)


def _ensure_not_stopped(stop_checker: StopChecker | None) -> None:
    if stop_checker and stop_checker():
        raise InterruptedError("导出流程已被中断")


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
    filter_decorative_fragments: bool = True,
    split_mode: str = "classic",
    skip_enhance: bool = False,
    skip_transparent: bool = False,
    stage_logger: StageLogger | None = None,
    page_logger: PageLogger | None = None,
    stop_checker: StopChecker | None = None,
) -> dict[str, Any]:
    """为新主路径准备分割后的元素资产。"""
    work_dir.mkdir(parents=True, exist_ok=True)
    page_summaries: list[dict[str, Any]] = []
    for page in sorted(project.get("pages", []), key=lambda item: int(item.get("page_no", 0))):
        _ensure_not_stopped(stop_checker)
        page_no = int(page.get("page_no", 0))
        if page_no <= 0:
            continue
        visual_image = Path(str(page.get("visual_image", "")))
        reference_image = Path(str(page.get("reference_image", "")))
        if not visual_image.exists():
            raise FileNotFoundError(f"第 {page_no} 页元素图不存在：{visual_image}")
        if not reference_image.exists():
            raise FileNotFoundError(f"第 {page_no} 页参考图不存在：{reference_image}")

        image_width, image_height = resolve_canvas_size(reference_image, visual_image)
        asset_result = prepare_direct_page_assets(
            work_dir=work_dir,
            page_no=page_no,
            elements_image=visual_image,
            image_width=image_width,
            image_height=image_height,
            alpha_threshold=alpha_threshold,
            min_area=min_area,
            min_width=min_width,
            min_height=min_height,
            padding=padding,
            merge_distance=merge_distance,
            filter_decorative_fragments=filter_decorative_fragments,
            split_mode=split_mode,
            skip_enhance=skip_enhance,
            skip_transparent=skip_transparent,
        )
        manifest = dict(asset_result["manifest"])
        _log_page(page_logger, page_no, f"已准备分割元素资产，共 {int(manifest.get('count', 0))} 个元素")
        page_summaries.append(
            {
                "page_no": page_no,
                "asset_count": int(manifest.get("count", 0)),
                "assets_manifest": str(asset_result["manifest_path"]),
                "processing": {
                    "page_no": page_no,
                    "source_image": str(visual_image),
                    "asset_strategy": "direct_split_elements",
                    "merge_distance": int(merge_distance),
                    "filter_decorative_fragments": bool(filter_decorative_fragments),
                    "split_mode": str(split_mode),
                },
            }
        )
    _log(stage_logger, f"分割元素资产准备完成，共 {len(page_summaries)} 页")
    return {
        "page_count": len(page_summaries),
        "pages": page_summaries,
    }


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
    filter_decorative_fragments: bool = True,
    split_mode: str = "classic",
    skip_enhance: bool = False,
    skip_transparent: bool = False,
    stage_logger: StageLogger | None = None,
    page_logger: PageLogger | None = None,
    stop_checker: StopChecker | None = None,
) -> dict[str, Any]:
    """按页执行参考图+元素图首轮和真实导出回看修正，生成整套项目脚本。"""
    assets_summary = prepare_direct_project_assets(
        project,
        work_dir,
        alpha_threshold=alpha_threshold,
        min_area=min_area,
        min_width=min_width,
        min_height=min_height,
        padding=padding,
        merge_distance=merge_distance,
        filter_decorative_fragments=filter_decorative_fragments,
        split_mode=split_mode,
        skip_enhance=skip_enhance,
        skip_transparent=skip_transparent,
        stage_logger=stage_logger,
        page_logger=page_logger,
        stop_checker=stop_checker,
    )
    page_scripts: list[dict[str, Any]] = []
    page_results: list[dict[str, Any]] = []

    for page in sorted(project.get("pages", []), key=lambda item: int(item.get("page_no", 0))):
        _ensure_not_stopped(stop_checker)
        page_no = int(page.get("page_no", 0))
        if page_no <= 0:
            continue

        reference_image = Path(str(page.get("reference_image", "")))
        visual_image = Path(str(page.get("visual_image", "")))
        if not reference_image.exists():
            raise FileNotFoundError(f"第 {page_no} 页参考图不存在：{reference_image}")
        if not visual_image.exists():
            raise FileNotFoundError(f"第 {page_no} 页元素图不存在：{visual_image}")

        page_dir = work_dir / f"page_{page_no:02d}"
        image_width, image_height = resolve_canvas_size(reference_image, visual_image)
        single_page_project = build_direct_single_page_project(
            reference_image=reference_image,
            elements_image=visual_image,
            image_width=image_width,
            image_height=image_height,
            slide_width_inch=float(project.get("slide_width_inch", 13.333333)),
            page_no=page_no,
        )
        single_page_project["asset_adjustments"] = {str(page_no): {}}
        _log_page(page_logger, page_no, "开始直出首轮文字脚本")
        current_script = _request_direct_page_script(
            provider,
            reference_image=reference_image,
            elements_image=visual_image,
            image_width=image_width,
            image_height=image_height,
        )
        current_asset_adjustments: dict[str, Any] = {}

        page_result = {
            "page_no": page_no,
            "office_render_available": False,
            "refine_rounds_applied": 0,
            "office_preview_paths": [],
            "comparison_paths": [],
        }

        for round_index in range(max(0, int(refine_rounds))):
            _ensure_not_stopped(stop_checker)
            preview_pptx = page_dir / f"render_preview_round_{round_index + 1:02d}.pptx"
            preview_script_path = page_dir / f"generated_text_layout_preview_round_{round_index + 1:02d}.py"
            _write_direct_page_script(
                project=single_page_project,
                work_dir=work_dir,
                output_pptx=preview_pptx,
                page_no=page_no,
                page_script=current_script,
                script_path=preview_script_path,
            )
            execute_generated_text_script(preview_script_path)

            preview_image_path = page_dir / f"office_preview_round_{round_index + 1:02d}.png"
            rendered_preview = render_pptx_first_slide_to_png(
                preview_pptx,
                preview_image_path,
                image_width=image_width,
                image_height=image_height,
            )
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
            refine_result = _refine_direct_page_script(
                provider,
                reference_image=reference_image,
                rendered_preview=rendered_preview,
                image_width=image_width,
                image_height=image_height,
                page_script=current_script,
                asset_adjustments=current_asset_adjustments,
                round_index=round_index,
            )
            candidate_script = refine_result.page_script
            candidate_adjustments = refine_result.asset_adjustments
            if candidate_script == current_script and candidate_adjustments == current_asset_adjustments:
                _log_page(page_logger, page_no, "修正轮未返回更优脚本，保留当前结果")
                break
            current_script = candidate_script
            current_asset_adjustments = candidate_adjustments
            single_page_project["asset_adjustments"] = {str(page_no): dict(current_asset_adjustments)}
            page_result["refine_rounds_applied"] = int(page_result["refine_rounds_applied"]) + 1

        page_scripts.append(
            {
                "page_no": page_no,
                "script": current_script,
                "asset_adjustments": dict(current_asset_adjustments),
            }
        )
        if page_result["office_preview_paths"]:
            manifest_path = page_dir / "assets" / "assets.json"
            overlap_report = analyze_text_asset_overlaps(
                manifest_path=manifest_path,
                page_script=current_script,
                current_adjustments=current_asset_adjustments,
            )
            page_result["text_asset_overlap"] = {
                "total_boxes": int(overlap_report.total_boxes),
                "overlap_box_count": int(overlap_report.overlap_box_count),
                "overlap_ratio": float(overlap_report.overlap_ratio),
                "max_overlap_pixels": int(overlap_report.max_overlap_pixels),
                "overlapping_box_indices": list(overlap_report.overlapping_box_indices),
            }
            alignment_decision = analyze_global_asset_alignment(
                reference_image=reference_image,
                manifest_path=manifest_path,
                page_script=current_script,
                current_adjustments=current_asset_adjustments,
            )
            page_result["asset_alignment_decision"] = {
                "should_apply": bool(alignment_decision.should_apply),
                "dx": int(alignment_decision.dx),
                "dy": int(alignment_decision.dy),
                "baseline_iou": float(alignment_decision.baseline_iou),
                "shifted_iou": float(alignment_decision.shifted_iou),
                "confidence": float(alignment_decision.confidence),
                "reason": alignment_decision.reason,
            }
            should_trigger_third_round = (
                overlap_report.overlap_ratio >= 0.25
                or overlap_report.overlap_box_count >= 2
                or overlap_report.max_overlap_pixels >= 120
            )
            if should_trigger_third_round and alignment_decision.should_apply:
                page_scripts[-1]["asset_adjustments"] = alignment_decision.suggested_adjustments
                _log_page(
                    page_logger,
                    page_no,
                    f"已应用第三轮元素对齐：dx={alignment_decision.dx}, dy={alignment_decision.dy}",
                )
            elif should_trigger_third_round:
                _log_page(
                    page_logger,
                    page_no,
                    f"检测到文字与元素重叠，但未形成稳定全局偏移，跳过第三轮全局对齐：{alignment_decision.reason}",
                )
        page_results.append(page_result)

    script_path = work_dir / "generated_text_layout.py"
    script_source = build_project_script_source(
        project,
        work_dir,
        output_pptx,
        page_scripts,
        include_assets=True,
    )
    script_path.write_text(script_source, encoding="utf-8")
    return {
        "script_path": str(script_path),
        "assets": assets_summary,
        "pages": page_results,
    }
