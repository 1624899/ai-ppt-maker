from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from ppt_system.composer import compose_pptx
from ppt_system.image_ops import enhance_image, make_transparent
from ppt_system.splitter import split_transparent_png
from ppt_system.text_layout import (
    build_fallback_boxes_for_family,
    build_layout_slots_by_family,
    build_text_boxes_from_slots,
)


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


def rebuild_page_texts(page: dict[str, Any], image_width: int, image_height: int) -> list[dict[str, Any]]:
    texts = page.get("texts", [])
    if isinstance(texts, list) and texts:
        return texts

    title = str(page.get("title", "")).strip() or f"第 {page.get('page_no', '?')} 页"
    body = _build_body_text(page)
    layout_family = str(page.get("layout_family", "split_left_right")).strip() or "split_left_right"
    layout_slots = page.get("layout_slots", [])

    rebuilt: list[dict[str, Any]] = []
    if isinstance(layout_slots, list) and layout_slots:
        rebuilt = build_text_boxes_from_slots(layout_slots, title, body, image_width, image_height)
    if not rebuilt:
        slots = build_layout_slots_by_family(layout_family, image_width, image_height)
        rebuilt = build_text_boxes_from_slots(slots, title, body, image_width, image_height)
    if rebuilt and len(rebuilt) > 1:
        return rebuilt
    return build_fallback_boxes_for_family(layout_family, title, body, image_width, image_height)


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
        # Web 层暴露给前端的是 /runs/<job_id>/...，这里统一还原回任务目录中的真实文件。
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

    element_map = {
        int(item["page_no"]): item
        for item in job.get("element_pages", [])
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

        visual_path = resolve_job_artifact_path(job_dir, str(element_item["image"]))
        if not visual_path.exists():
            raise FileNotFoundError(f"第 {page_no} 页元素图不存在：{visual_path}")

        project_pages.append(
            {
                "page_no": page_no,
                "title": str(raw_page.get("title", f"第 {page_no} 页")),
                "summary": str(raw_page.get("summary", "")),
                "visual_image": str(visual_path),
                "texts": rebuild_page_texts(raw_page, image_width, image_height),
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
            "color": "FFFFFF",
            "bold": False,
            "italic": False,
            "align": "LEFT",
        },
        "pages": project_pages,
    }


def prepare_project_assets(
    project: dict[str, Any],
    work_dir: Path,
    *,
    alpha_threshold: int = 8,
    min_area: int = 8,
    padding: int = 0,
    skip_enhance: bool = False,
    skip_transparent: bool = False,
    stage_logger: StageLogger | None = None,
    page_logger: PageLogger | None = None,
    stop_checker: StopChecker | None = None,
) -> dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True)
    page_summaries: list[dict[str, Any]] = []

    for page in sorted(project.get("pages", []), key=lambda item: int(item.get("page_no", 0))):
        _ensure_not_stopped(stop_checker)

        page_no = int(page["page_no"])
        page_dir = work_dir / f"page_{page_no:02d}"
        assets_dir = page_dir / "assets"
        manifest_path = assets_dir / "assets.json"

        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            _log_page(page_logger, page_no, f"复用已有切分结果，共 {int(manifest.get('count', 0))} 个元素")
            page_summaries.append(
                {
                    "page_no": page_no,
                    "asset_count": int(manifest.get("count", 0)),
                    "assets_manifest": str(manifest_path),
                }
            )
            continue

        page_dir.mkdir(parents=True, exist_ok=True)
        visual_path = Path(str(page["visual_image"]))
        enhanced_path = page_dir / "01_enhanced.png"
        transparent_path = page_dir / "02_transparent.png"

        _log(stage_logger, f"开始处理第 {page_no} 页导出素材")
        if skip_enhance:
            enhanced_path = visual_path
            _log_page(page_logger, page_no, "跳过图像增强")
        else:
            _log_page(page_logger, page_no, "执行图像增强")
            enhance_image(visual_path, enhanced_path)

        _ensure_not_stopped(stop_checker)

        if skip_transparent:
            transparent_path = enhanced_path
            _log_page(page_logger, page_no, "跳过去背景处理")
        else:
            _log_page(page_logger, page_no, "执行背景透明化")
            make_transparent(enhanced_path, transparent_path)

        _ensure_not_stopped(stop_checker)

        _log_page(page_logger, page_no, "执行连通域切分")
        manifest = split_transparent_png(
            image_path=transparent_path,
            out_dir=assets_dir,
            alpha_threshold=alpha_threshold,
            min_area=min_area,
            padding=padding,
        )
        _log_page(page_logger, page_no, f"切分完成，共 {int(manifest.get('count', 0))} 个元素")
        page_summaries.append(
            {
                "page_no": page_no,
                "asset_count": int(manifest.get("count", 0)),
                "assets_manifest": str(manifest_path),
            }
        )

    return {
        "page_count": len(page_summaries),
        "pages": page_summaries,
    }


def export_project_to_pptx(
    project: dict[str, Any],
    work_dir: Path,
    output_pptx: Path,
    *,
    alpha_threshold: int = 8,
    min_area: int = 8,
    padding: int = 0,
    skip_enhance: bool = False,
    skip_transparent: bool = False,
    stage_logger: StageLogger | None = None,
    page_logger: PageLogger | None = None,
    stop_checker: StopChecker | None = None,
) -> dict[str, Any]:
    assets_summary = prepare_project_assets(
        project,
        work_dir,
        alpha_threshold=alpha_threshold,
        min_area=min_area,
        padding=padding,
        skip_enhance=skip_enhance,
        skip_transparent=skip_transparent,
        stage_logger=stage_logger,
        page_logger=page_logger,
        stop_checker=stop_checker,
    )
    _ensure_not_stopped(stop_checker)
    _log(stage_logger, "开始组装可编辑 PPTX")
    compose_pptx(project, work_dir, output_pptx)
    _log(stage_logger, f"PPTX 已导出：{output_pptx.name}")
    return {
        "output_pptx": str(output_pptx),
        "work_dir": str(work_dir),
        "assets": assets_summary,
    }


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
    alpha_threshold: int = 8,
    min_area: int = 8,
    padding: int = 0,
    skip_enhance: bool = False,
    skip_transparent: bool = False,
    stage_logger: StageLogger | None = None,
    page_logger: PageLogger | None = None,
    stop_checker: StopChecker | None = None,
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

    export_summary = export_project_to_pptx(
        project,
        work_dir,
        output_pptx,
        alpha_threshold=alpha_threshold,
        min_area=min_area,
        padding=padding,
        skip_enhance=skip_enhance,
        skip_transparent=skip_transparent,
        stage_logger=stage_logger,
        page_logger=page_logger,
        stop_checker=stop_checker,
    )
    job_id = str(job.get("job_id") or job_dir.name)
    return {
        "project_path": str(project_path),
        "project_url": f"/runs/{job_id}/{project_path.relative_to(job_dir).as_posix()}",
        "pptx_path": str(output_pptx),
        "pptx_url": f"/runs/{job_id}/{output_pptx.relative_to(job_dir).as_posix()}",
        "work_dir": str(work_dir),
        "page_count": len(project.get("pages", [])),
        "assets": export_summary.get("assets", {}),
    }
