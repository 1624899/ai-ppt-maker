from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ppt_system.image.canvas_normalization import normalize_image_canvas
from ppt_system.image.image_ops import enhance_image, make_transparent
from ppt_system.image.splitter import split_transparent_png
from ppt_system.image.text_placeholder_detection import save_text_placeholders

from skill_core.project import resolve_project_path


def selected_pages(project: dict[str, Any], page_numbers: list[int] | None) -> list[dict[str, Any]]:
    pages = project["pages"]
    if page_numbers is None:
        return pages
    requested = set(page_numbers)
    selected = [page for page in pages if int(page["page_no"]) in requested]
    missing = requested - {int(page["page_no"]) for page in selected}
    if missing:
        raise ValueError("项目中没有这些页码：" + "、".join(map(str, sorted(missing))))
    return selected


def normalize_references(
    project: dict[str, Any],
    project_path: Path,
    work_dir: Path,
    page_numbers: list[int] | None = None,
) -> list[dict[str, Any]]:
    width = int(project["canvas"]["width"])
    height = int(project["canvas"]["height"])
    results: list[dict[str, Any]] = []
    for page in selected_pages(project, page_numbers):
        page_no = int(page["page_no"])
        source = resolve_project_path(project_path, str(page.get("reference_image", "")))
        if not source.is_file():
            raise FileNotFoundError(f"第 {page_no} 页原稿图不存在：{source}")
        target = work_dir / f"page_{page_no:02d}" / "reference.png"
        result = normalize_image_canvas(
            source,
            target,
            target_width=width,
            target_height=height,
            resize_mode=str(page.get("resize_mode", "auto")),
            background=str(page.get("background_color") or project.get("background_color") or "#FFFFFF"),
            flatten=True,
        )
        results.append({"page_no": page_no, "reference_image": str(target.resolve()), "normalization": result.as_dict()})
    return results


def prepare_images(
    project: dict[str, Any],
    project_path: Path,
    work_dir: Path,
    *,
    page_numbers: list[int] | None = None,
    workers: int = 1,
    min_asset_area: int = 8,
) -> list[dict[str, Any]]:
    width = int(project["canvas"]["width"])
    height = int(project["canvas"]["height"])
    pages = selected_pages(project, page_numbers)
    normalize_references(project, project_path, work_dir, [int(page["page_no"]) for page in pages])

    def prepare_page(page: dict[str, Any]) -> dict[str, Any]:
        page_no = int(page["page_no"])
        page_dir = work_dir / f"page_{page_no:02d}"
        source = resolve_project_path(project_path, str(page.get("elements_image", "")))
        if not source.is_file():
            raise FileNotFoundError(f"第 {page_no} 页元素图不存在：{source}")
        elements_path = page_dir / "elements.png"
        normalize_image_canvas(
            source,
            elements_path,
            target_width=width,
            target_height=height,
            resize_mode=str(page.get("elements_resize_mode", "stretch")),
            background=str(page.get("background_color") or project.get("background_color") or "#FFFFFF"),
        )
        placeholders_path = page_dir / "text_placeholders.json"
        placeholders = save_text_placeholders(page_dir / "reference.png", elements_path, placeholders_path)
        enhanced_path = enhance_image(elements_path, page_dir / "elements.enhanced.png")
        transparent = make_transparent(enhanced_path, page_dir / "elements.transparent.png")
        manifest = split_transparent_png(
            transparent.output_path,
            page_dir / "assets",
            min_area=min_asset_area,
        )
        return {
            "page_no": page_no,
            "reference_image": str((page_dir / "reference.png").resolve()),
            "elements_image": str(elements_path.resolve()),
            "transparent_image": str(transparent.output_path.resolve()),
            "transparency_strategy": transparent.strategy,
            "transparency_warning": transparent.warning,
            "placeholders": str(placeholders_path.resolve()),
            "placeholder_count": len(placeholders.get("placeholders", [])),
            "asset_manifest": str((page_dir / "assets" / "assets.json").resolve()),
            "asset_count": int(manifest["count"]),
        }

    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as executor:
        results = list(executor.map(prepare_page, pages))
    return sorted(results, key=lambda item: item["page_no"])
