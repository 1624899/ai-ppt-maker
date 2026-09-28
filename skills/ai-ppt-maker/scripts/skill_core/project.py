from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from ppt_system.generation.design_grammar import (
    ALLOWED_LAYOUT_FAMILIES,
    compress_style_for_prompt,
    normalize_design_grammar,
)
from ppt_system.generation.source_content_anchors import build_source_content_anchors


NUMERIC_PATTERN = re.compile(r"(?<![0-9A-Za-z])\d+(?:[.,]\d+)*(?:[%％])?")
DATE_PATTERN = re.compile(r"\d{4}\s*年\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?")


def read_project(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("项目文件顶层必须是 JSON 对象。")
    return payload


def read_source(path: Path | None) -> str:
    return path.read_text(encoding="utf-8") if path is not None else ""


def collect_anchors(source: str, page_count: int) -> list[dict[str, Any]]:
    return build_source_content_anchors(source, page_count) if source.strip() else []


def page_text(page: dict[str, Any], *, rendered: bool) -> str:
    if rendered:
        return "\n".join(
            str(box.get("text", ""))
            for box in page.get("text_boxes", [])
            if isinstance(box, dict)
        )
    return "\n".join(
        [
            str(page.get("title", "")),
            str(page.get("summary", "")),
            *[str(item) for item in page.get("bullets", [])],
        ]
    )


def _normalize_for_compare(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def _numeric_facts(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", value)
    return set(NUMERIC_PATTERN.findall(normalized)) | {
        _normalize_for_compare(item) for item in DATE_PATTERN.findall(normalized)
    }


def validate_project(
    project: dict[str, Any],
    *,
    source: str = "",
    require_text_boxes: bool = False,
    text_page_numbers: list[int] | None = None,
) -> list[str]:
    errors: list[str] = []
    canvas = project.get("canvas")
    if not isinstance(canvas, dict):
        return ["缺少 canvas 对象。"]
    try:
        width, height = int(canvas["width"]), int(canvas["height"])
    except (KeyError, TypeError, ValueError):
        return ["canvas.width 与 canvas.height 必须是正整数。"]
    if width <= 0 or height <= 0:
        errors.append("canvas.width 与 canvas.height 必须大于 0。")

    style_guide = project.get("style_guide")
    if not isinstance(style_guide, dict) or not style_guide.get("style_name") or not isinstance(style_guide.get("style_core"), dict):
        errors.append("style_guide 需要 style_name 和 style_core。")
    if project.get("source_mode", "text") not in {"text", "external_reference"}:
        errors.append("source_mode 只能是 text 或 external_reference。")
    if project.get("source_mode", "text") == "text" and not source.strip():
        errors.append("文本生成需要 source_file 或 --source 指向原始长文。")
    required_terms = project.get("required_terms", [])
    if not isinstance(required_terms, list):
        errors.append("required_terms 必须是数组。")
        required_terms = []

    pages = project.get("pages")
    if not isinstance(pages, list) or not pages:
        return errors + ["pages 必须包含至少一页。"]
    selected_text_pages = set(text_page_numbers) if text_page_numbers is not None else set(range(1, len(pages) + 1))
    unknown_text_pages = selected_text_pages - set(range(1, len(pages) + 1))
    if unknown_text_pages:
        errors.append("不存在的页码：" + "、".join(map(str, sorted(unknown_text_pages))))

    families: list[str] = []
    assigned_anchors: set[str] = set()
    anchors = collect_anchors(source, len(pages))
    anchor_ids = {str(item["id"]) for item in anchors}
    for index, page in enumerate(pages, start=1):
        if not isinstance(page, dict):
            errors.append(f"第 {index} 页必须是 JSON 对象。")
            continue
        if page.get("page_no") != index:
            errors.append(f"第 {index} 页的 page_no 必须为 {index}。")
        if not str(page.get("title", "")).strip():
            errors.append(f"第 {index} 页缺少 title。")
        if not isinstance(page.get("bullets", []), list):
            errors.append(f"第 {index} 页的 bullets 必须是数组。")
        family = str(page.get("layout_family", "")).strip()
        if family not in ALLOWED_LAYOUT_FAMILIES:
            errors.append(f"第 {index} 页的 layout_family 未知：{family}")
        families.append(family)
        if index > 1 and family == families[-2]:
            errors.append(f"第 {index - 1} 页与第 {index} 页的版式家族相同。")

        raw_ids = page.get("source_anchor_ids", [])
        if not isinstance(raw_ids, list):
            errors.append(f"第 {index} 页的 source_anchor_ids 必须是数组。")
            raw_ids = []
        for raw_id in raw_ids:
            anchor_id = str(raw_id)
            if anchor_ids and anchor_id not in anchor_ids:
                errors.append(f"第 {index} 页引用了不存在的事实锚点 {anchor_id}。")
            assigned_anchors.add(anchor_id)

        if require_text_boxes and index in selected_text_pages:
            boxes = page.get("text_boxes")
            if not isinstance(boxes, list) or not boxes:
                errors.append(f"第 {index} 页缺少可编辑 text_boxes。")
            else:
                errors.extend(_validate_text_boxes(index, boxes, width, height))

    distinct_required = min(3, len(pages))
    if len(set(families)) < distinct_required:
        errors.append(f"当前页数需要至少 {distinct_required} 种版式家族。")
    missing_anchors = anchor_ids - assigned_anchors
    if missing_anchors:
        errors.append("未分配的事实锚点：" + "、".join(sorted(missing_anchors)))

    for rendered in (False, True) if require_text_boxes else (False,):
        target_pages = [
            page for page_index, page in enumerate(pages, start=1)
            if isinstance(page, dict) and (not rendered or page_index in selected_text_pages)
        ]
        combined = "\n".join(page_text(page, rendered=rendered) for page in target_pages)
        target = "可编辑文字层" if rendered else "逐页规划"
        checked_source = source
        checked_terms = required_terms
        if rendered and len(selected_text_pages) < len(pages):
            selected_ids = {
                str(anchor_id)
                for page in target_pages
                for anchor_id in page.get("source_anchor_ids", [])
            }
            checked_source = "\n".join(
                str(anchor.get("source_text", "")) for anchor in anchors if str(anchor.get("id", "")) in selected_ids
            )
            planned_selected = _normalize_for_compare("\n".join(page_text(page, rendered=False) for page in target_pages))
            checked_terms = [term for term in required_terms if _normalize_for_compare(str(term)) in planned_selected]
        missing_numbers = _numeric_facts(checked_source) - _numeric_facts(combined)
        if missing_numbers:
            errors.append(f"{target}缺少源文数字或日期：" + "、".join(sorted(missing_numbers)))
        normalized_combined = _normalize_for_compare(combined)
        for term in checked_terms:
            if _normalize_for_compare(str(term)) not in normalized_combined:
                errors.append(f"{target}缺少业务原词：{term}")
    return errors


def _validate_text_boxes(page_no: int, boxes: list[Any], width: int, height: int) -> list[str]:
    errors: list[str] = []
    for index, box in enumerate(boxes, start=1):
        prefix = f"第 {page_no} 页第 {index} 个文本框"
        if not isinstance(box, dict) or not str(box.get("text", "")).strip():
            errors.append(f"{prefix}缺少 text。")
            continue
        try:
            left = float(box["left"])
            top = float(box["top"])
            box_width = float(box["width"])
            box_height = float(box["height"])
            font_size = float(box["font_size"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"{prefix}的坐标、尺寸或字号无效。")
            continue
        if min(left, top) < 0 or box_width <= 0 or box_height <= 0 or font_size <= 0:
            errors.append(f"{prefix}必须位于画布内且具有正尺寸和字号。")
        if left + box_width > width or top + box_height > height:
            errors.append(f"{prefix}超出了画布。")
    return errors


def build_prompts(project: dict[str, Any]) -> list[dict[str, Any]]:
    canvas = project["canvas"]
    width, height = int(canvas["width"]), int(canvas["height"])
    raw_style = project["style_guide"]
    style = normalize_design_grammar(raw_style)
    compression = str(raw_style.get("prompt_compression", "compressed"))
    max_chars = int(raw_style.get("prompt_max_chars", 1800))
    prompts: list[dict[str, Any]] = []
    for page in project["pages"]:
        exact_text = page_text(page, rendered=False)
        style_prompt = compress_style_for_prompt(
            style,
            mode=compression,
            max_chars=max_chars,
            layout_family_override=str(page["layout_family"]),
            difference_override=str(page.get("difference_from_previous", "")),
        )
        reference_prompt = "\n".join(
            [
                f"生成 {width}x{height} 的完整 PPT 页面原稿图。",
                style_prompt,
                f"页面主题：{page['title']}",
                f"画面内容：{page.get('visual_brief', '')}",
                "以下文字必须准确呈现，不增删数字、日期和业务用语：",
                exact_text,
                "让页面的文字和元素形成完整构图，保持与同一套演示文稿的视觉语言一致。",
            ]
        )
        elements_prompt = "\n".join(
            [
                "以本页原稿图为编辑目标，只移除全部文字字形，保留图形、图标、照片、容器、颜色、位置、比例和留白。",
                "不要新增或挪动元素，不要改变画幅；尽量输出透明背景，若不能透明则使用可分离的纯净底色。",
                f"目标画幅：{width}x{height}。",
            ]
        )
        prompts.append(
            {
                "page_no": int(page["page_no"]),
                "style_reference_images": project.get("style_reference_images", []),
                "reference_prompt": reference_prompt,
                "elements_prompt": elements_prompt,
            }
        )
    return prompts


def resolve_project_path(project_path: Path, raw_path: str) -> Path:
    candidate = Path(str(raw_path).strip()).expanduser()
    if not str(raw_path).strip():
        raise ValueError("图片路径为空。")
    return (candidate if candidate.is_absolute() else project_path.parent / candidate).resolve()
