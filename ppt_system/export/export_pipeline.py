from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from ppt_system.export.delivery_options import (
    SEPARATE_DELIVERY_MODE,
    build_editable_delivery_description,
    build_editable_delivery_label,
    normalize_editable_delivery_layer_mode,
)
from ppt_system.export.direct_project_script import generate_direct_project_text_script
from ppt_system.export.editable_delivery_bundle import (
    export_editable_delivery_from_bundle,
    write_editable_delivery_bundle,
)
from ppt_system.export.export_layer_mode import SEPARATE_LAYER_MODE, count_output_slides
from ppt_system.integrations.openai_chat_provider import OpenAIChatProvider
from ppt_system.generation.style_runtime import apply_text_theme, resolve_text_palette
from ppt_system.generation.text_layout import (
    build_fallback_boxes_for_family,
    build_layout_slots_by_family,
    build_text_boxes_from_slots,
)
from ppt_system.export.text_script_runtime import execute_generated_text_script


StageLogger = Callable[[str], None]
PageLogger = Callable[[int, str], None]
StopChecker = Callable[[], bool]


def _log(stage_logger: StageLogger | None, message: str) -> None:
    if stage_logger:
        stage_logger(message)


def _ensure_not_stopped(stop_checker: StopChecker | None) -> None:
    if stop_checker and stop_checker():
        raise InterruptedError("导出流程已被中断")


def _build_body_text(page: dict[str, Any]) -> str:
    bullets = page.get("bullets", [])
    if isinstance(bullets, list):
        normalized = [str(item).strip() for item in bullets if str(item).strip()]
        if normalized:
            return "\n".join(f"• {item}" for item in normalized[:5])

    summary = str(page.get("summary", "")).strip()
    if summary:
        lines = [item.strip() for item in summary.splitlines() if item.strip()]
        if lines:
            return "\n".join(f"• {item}" for item in lines[:5])
        return summary
    return ""


def rebuild_page_texts(
    page: dict[str, Any],
    image_width: int,
    image_height: int,
    style_guide: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    texts = page.get("texts", [])
    if isinstance(texts, list) and texts:
        return apply_text_theme(texts, style_guide)

    title = str(page.get("title", "")).strip() or f"第 {page.get('page_no', '?')} 页"
    body = _build_body_text(page)
    layout_family = str(page.get("layout_family", "split_left_right")).strip() or "split_left_right"
    layout_slots = page.get("layout_slots")

    rebuilt: list[dict[str, Any]] = []
    if isinstance(layout_slots, dict) and isinstance(layout_slots.get("slot_coords"), dict):
        rebuilt = build_text_boxes_from_slots(layout_slots, title, body, image_width, image_height)
    if not rebuilt:
        slots = build_layout_slots_by_family(layout_family, image_width, image_height)
        rebuilt = build_text_boxes_from_slots(slots, title, body, image_width, image_height)
    if rebuilt and len(rebuilt) > 1:
        return apply_text_theme(rebuilt, style_guide)
    fallback = build_fallback_boxes_for_family(layout_family, title, body, image_width, image_height)
    return apply_text_theme(fallback, style_guide)


def resolve_job_artifact_path(job_dir: Path, image_ref: str) -> Path:
    value = str(image_ref).strip()
    if not value:
        raise ValueError("页面视觉图路径为空")

    candidate = Path(value)
    if candidate.is_absolute():
        return candidate

    normalized = value.lstrip("/\\")
    parts = Path(normalized).parts
    if len(parts) >= 3 and parts[0] == "runs":
        return job_dir / Path(*parts[2:])
    return job_dir / normalized


def build_project_from_web_job(
    job: dict[str, Any],
    job_dir: Path,
    *,
    title: str,
    image_width: int,
    image_height: int,
) -> dict[str, Any]:
    raw_pages = list(job.get("pages", []))
    if not raw_pages:
        raise ValueError("任务中缺少页面规划结果，无法导出 PPT")
    plan = job.get("plan", {})
    style_guide = plan.get("style_guide", {}) if isinstance(plan, dict) else {}
    text_palette = resolve_text_palette(style_guide)

    element_map = {
        int(item["page_no"]): item
        for item in job.get("element_pages", [])
        if str(item.get("image", "")).strip()
    }
    reference_map = {
        int(item["page_no"]): item
        for item in job.get("reference_pages", [])
        if str(item.get("image", "")).strip()
    }
    project_pages: list[dict[str, Any]] = []

    for raw_page in sorted(raw_pages, key=lambda item: int(item.get("page_no", 0))):
        page_no = int(raw_page.get("page_no", 0))
        if page_no <= 0:
            continue

        element_item = element_map.get(page_no)
        if not element_item:
            raise ValueError(f"第 {page_no} 页缺少去文字元素图，无法继续导出")
        reference_item = reference_map.get(page_no)
        if not reference_item:
            raise ValueError(f"第 {page_no} 页缺少原稿图，无法继续导出")

        visual_path = resolve_job_artifact_path(job_dir, str(element_item["image"]))
        reference_path = resolve_job_artifact_path(job_dir, str(reference_item["image"]))
        if not visual_path.exists():
            raise FileNotFoundError(f"第 {page_no} 页元素图不存在：{visual_path}")
        if not reference_path.exists():
            raise FileNotFoundError(f"第 {page_no} 页原稿图不存在：{reference_path}")

        rebuilt_texts = rebuild_page_texts(raw_page, image_width, image_height, style_guide)
        project_pages.append(
            {
                "page_no": page_no,
                "title": str(raw_page.get("title", f"第 {page_no} 页")),
                "summary": str(raw_page.get("summary", "")),
                "bullets": list(raw_page.get("bullets", [])) if isinstance(raw_page.get("bullets"), list) else [],
                "visual_image": str(visual_path),
                "reference_image": str(reference_path),
                "texts": rebuilt_texts,
                "layout_family": str(raw_page.get("layout_family", "")),
            }
        )

    return {
        "title": title or "自动生成 PPT",
        "content": str(job.get("content", "")),
        "style_images": [],
        "slide_width_inch": 13.333333,
        "image_width": image_width,
        "image_height": image_height,
        "default_font": {
            "font_name": "Microsoft YaHei",
            "font_size": 24,
            "color": text_palette["default"],
            "bold": False,
            "italic": False,
            "align": "LEFT",
        },
        "pages": project_pages,
    }


def export_project_to_pptx(
    project: dict[str, Any],
    work_dir: Path,
    output_pptx: Path,
    *,
    script_refine_rounds: int = 1,
    alpha_threshold: int = 8,
    min_area: int = 8,
    min_width: int = 0,
    min_height: int = 0,
    padding: int = 0,
    merge_distance: int = 6,
    skip_enhance: bool = False,
    skip_transparent: bool = False,
    export_page_concurrency: int = 1,
    chat_provider: OpenAIChatProvider | None = None,
    stage_logger: StageLogger | None = None,
    page_logger: PageLogger | None = None,
    stop_checker: StopChecker | None = None,
) -> dict[str, Any]:
    export_summary = _prepare_editable_delivery_core(
        project,
        work_dir,
        output_pptx,
        script_refine_rounds=script_refine_rounds,
        alpha_threshold=alpha_threshold,
        min_area=min_area,
        min_width=min_width,
        min_height=min_height,
        padding=padding,
        merge_distance=merge_distance,
        skip_enhance=skip_enhance,
        skip_transparent=skip_transparent,
        export_page_concurrency=export_page_concurrency,
        chat_provider=chat_provider,
        stage_logger=stage_logger,
        page_logger=page_logger,
        stop_checker=stop_checker,
    )
    generated_script_path = Path(str(export_summary["text_script_path"]))
    execute_generated_text_script(generated_script_path)
    _log(stage_logger, f"文字脚本执行完成：{output_pptx.name}")
    return export_summary


def _prepare_editable_delivery_core(
    project: dict[str, Any],
    work_dir: Path,
    output_pptx: Path,
    *,
    script_refine_rounds: int = 1,
    alpha_threshold: int = 8,
    min_area: int = 8,
    min_width: int = 0,
    min_height: int = 0,
    padding: int = 0,
    merge_distance: int = 6,
    skip_enhance: bool = False,
    skip_transparent: bool = False,
    export_page_concurrency: int = 1,
    chat_provider: OpenAIChatProvider | None = None,
    stage_logger: StageLogger | None = None,
    page_logger: PageLogger | None = None,
    stop_checker: StopChecker | None = None,
) -> dict[str, Any]:
    if chat_provider is None:
        raise RuntimeError("当前主路径必须提供 chat_provider，已不再支持 legacy/builtin 回退。")

    _log(stage_logger, "开始执行主路径：原稿图+元素图首轮直出，随后真实 PPT 导出回看")
    direct_result = generate_direct_project_text_script(
        chat_provider,
        project,
        work_dir,
        output_pptx,
        refine_rounds=script_refine_rounds,
        alpha_threshold=alpha_threshold,
        min_area=min_area,
        min_width=min_width,
        min_height=min_height,
        padding=padding,
        merge_distance=merge_distance,
        skip_enhance=skip_enhance,
        skip_transparent=skip_transparent,
        page_concurrency=export_page_concurrency,
        stage_logger=stage_logger,
        page_logger=page_logger,
        stop_checker=stop_checker,
    )
    _ensure_not_stopped(stop_checker)
    generated_script_path = Path(str(direct_result["script_path"]))
    _log(stage_logger, f"文字脚本已生成：{generated_script_path.name}")
    logical_page_count = len(project.get("pages", []))
    return {
        "output_pptx": str(output_pptx),
        "work_dir": str(work_dir),
        "assets": direct_result["assets"],
        "text_layout_strategy": "direct_office_refine",
        "text_script_path": str(generated_script_path),
        "page_results": direct_result["pages"],
        "page_scripts": direct_result.get("page_scripts", []),
        "delivery_mode": SEPARATE_DELIVERY_MODE,
        "logical_page_count": logical_page_count,
        "page_count": count_output_slides(logical_page_count, SEPARATE_LAYER_MODE),
        "layer_mode": SEPARATE_LAYER_MODE,
        "label": build_editable_delivery_label(SEPARATE_LAYER_MODE),
        "description": build_editable_delivery_description(SEPARATE_LAYER_MODE),
    }


def prepare_editable_delivery_bundle(
    project: dict[str, Any],
    work_dir: Path,
    output_pptx: Path,
    bundle_path: Path,
    *,
    script_refine_rounds: int = 1,
    alpha_threshold: int = 8,
    min_area: int = 8,
    min_width: int = 0,
    min_height: int = 0,
    padding: int = 0,
    merge_distance: int = 6,
    skip_enhance: bool = False,
    skip_transparent: bool = False,
    export_page_concurrency: int = 1,
    chat_provider: OpenAIChatProvider | None = None,
    stage_logger: StageLogger | None = None,
    page_logger: PageLogger | None = None,
    stop_checker: StopChecker | None = None,
) -> dict[str, Any]:
    export_summary = _prepare_editable_delivery_core(
        project,
        work_dir,
        output_pptx,
        script_refine_rounds=script_refine_rounds,
        alpha_threshold=alpha_threshold,
        min_area=min_area,
        min_width=min_width,
        min_height=min_height,
        padding=padding,
        merge_distance=merge_distance,
        skip_enhance=skip_enhance,
        skip_transparent=skip_transparent,
        export_page_concurrency=export_page_concurrency,
        chat_provider=chat_provider,
        stage_logger=stage_logger,
        page_logger=page_logger,
        stop_checker=stop_checker,
    )
    write_editable_delivery_bundle(
        bundle_path,
        project=project,
        work_dir=work_dir,
        page_scripts=list(export_summary.get("page_scripts", [])),
        assets=dict(export_summary.get("assets", {})),
        page_results=list(export_summary.get("page_results", [])),
        default_output_pptx=output_pptx,
        default_layer_mode=str(export_summary.get("layer_mode", SEPARATE_LAYER_MODE)),
    )
    export_summary["bundle_path"] = str(bundle_path)
    return export_summary


def export_editable_delivery(
    bundle_path: Path,
    output_pptx: Path,
    *,
    layer_mode: str,
) -> dict[str, Any]:
    return export_editable_delivery_from_bundle(
        bundle_path,
        output_pptx,
        layer_mode=normalize_editable_delivery_layer_mode(layer_mode),
    )


def export_web_job_to_pptx(
    job: dict[str, Any],
    job_dir: Path,
    *,
    title: str,
    image_width: int,
    image_height: int,
    work_dir: Path,
    output_pptx: Path,
    project_path: Path,
    bundle_path: Path,
    chat_provider: OpenAIChatProvider | None = None,
    stage_logger: StageLogger | None = None,
    page_logger: PageLogger | None = None,
    stop_checker: StopChecker | None = None,
    alpha_threshold: int = 8,
    min_area: int = 8,
    min_width: int = 0,
    min_height: int = 0,
    padding: int = 0,
    merge_distance: int = 6,
    skip_enhance: bool = False,
    skip_transparent: bool = False,
    script_refine_rounds: int = 1,
    export_page_concurrency: int = 1,
) -> dict[str, Any]:
    project = build_project_from_web_job(
        job,
        job_dir,
        title=title,
        image_width=image_width,
        image_height=image_height,
    )
    project_path.parent.mkdir(parents=True, exist_ok=True)
    project_path.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(stage_logger, f"已生成项目快照：{project_path.name}")

    export_summary = prepare_editable_delivery_bundle(
        project,
        work_dir,
        output_pptx,
        bundle_path,
        script_refine_rounds=script_refine_rounds,
        alpha_threshold=alpha_threshold,
        min_area=min_area,
        min_width=min_width,
        min_height=min_height,
        padding=padding,
        merge_distance=merge_distance,
        skip_enhance=skip_enhance,
        skip_transparent=skip_transparent,
        export_page_concurrency=export_page_concurrency,
        chat_provider=chat_provider,
        stage_logger=stage_logger,
        page_logger=page_logger,
        stop_checker=stop_checker,
    )
    job_id = str(job.get("job_id") or job_dir.name)
    return {
        "project_path": str(project_path),
        "project_url": f"/runs/{job_id}/{project_path.relative_to(job_dir).as_posix()}",
        "bundle_path": str(bundle_path),
        "bundle_url": f"/runs/{job_id}/{bundle_path.relative_to(job_dir).as_posix()}",
        "default_pptx_path": str(output_pptx),
        "default_pptx_url": f"/runs/{job_id}/{output_pptx.relative_to(job_dir).as_posix()}",
        "work_dir": str(work_dir),
        "page_count": int(export_summary.get("page_count", len(project.get("pages", [])))),
        "logical_page_count": int(export_summary.get("logical_page_count", len(project.get("pages", [])))),
        "assets": export_summary.get("assets", {}),
        "page_results": list(export_summary.get("page_results", [])),
        "text_script_path": str(export_summary.get("text_script_path", "")),
        "delivery_mode": str(export_summary.get("delivery_mode", SEPARATE_DELIVERY_MODE)),
        "layer_mode": str(export_summary.get("layer_mode", "")),
        "label": str(export_summary.get("label", "")),
        "description": str(export_summary.get("description", "")),
    }
