from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from ppt_system.export.export_layer_mode import OVERLAY_LAYER_MODE
from ppt_system.image.global_element_alignment import align_elements_image_to_reference
from ppt_system.image.image_alpha_profile import inspect_image_alpha
from ppt_system.image.image_ops import enhance_image, make_transparent
from ppt_system.image.intermediate_artifact_cleanup import cleanup_split_intermediate_images
from ppt_system.integrations.openai_chat_provider import OpenAIChatProvider
from ppt_system.export.ppt_calibration_renderer import render_pptx_first_slide_to_png
from ppt_system.image.splitter import split_transparent_png
from ppt_system.export.text_script_runtime import (
    build_project_script_source,
    execute_generated_text_script,
    normalize_asset_adjustments,
    normalize_page_script,
)
from ppt_system.image.text_placeholder_detection import placeholder_bboxes, save_text_placeholders
from ppt_system.runtime.interruptible_execution import run_interruptible_call


DEFAULT_SLIDE_WIDTH_INCH = 13.333333
DEFAULT_FONT_NAME = "Microsoft YaHei"
DEFAULT_FONT_COLOR = "355C7D"
StopChecker = Callable[[], bool]


def _ensure_not_stopped(stop_checker: StopChecker | None) -> None:
    if stop_checker and stop_checker():
        raise InterruptedError("导出流程已被中断")


@dataclass
class DirectPageScriptRevision:
    page_script: str
    asset_adjustments: dict[str, Any]


@dataclass(frozen=True)
class PreparedDirectPageAssets:
    manifest_path: str
    manifest: dict[str, Any]
    image_width: int
    image_height: int
    split_source_image: str
    transparent_preview_image: str | None
    removed_intermediate_images: list[str]
    global_alignment: dict[str, Any] | None
    asset_adjustments: dict[str, Any]


def resolve_canvas_size(reference_image: Path, elements_image: Path) -> tuple[int, int]:
    """优先读取原稿图尺寸，失败时退回元素图。"""
    errors: list[str] = []
    for image_path in (reference_image, elements_image):
        try:
            with Image.open(image_path) as image:
                return int(image.width), int(image.height)
        except Exception as exc:
            errors.append(f"{image_path}: {exc}")
    detail = "；".join(errors) if errors else "没有可用图片"
    raise RuntimeError(f"无法读取页面尺寸：{detail}")


def build_direct_page_prompt(
    *,
    image_width: int,
    image_height: int,
    text_placeholders: dict[str, Any] | None = None,
) -> str:
    """构建首轮依赖原稿图和元素图的单页脚本提示词。"""
    payload = {
        "canvas": {"width": int(image_width), "height": int(image_height)},
        "task": "single_page_text_only",
        "text_placeholders": []
        if not isinstance(text_placeholders, dict)
        else list(text_placeholders.get("placeholders", [])),
    }
    return (
        "第一张图是完整原稿图，第二张图是去文字后的元素图。"
        "系统已用 OpenCV 根据“原稿图 - 去文字元素图”估计出 text_placeholders。"
        "你的首要任务是识别并填写每个 placeholder 对应的真实文字内容。"
        "默认沿用 placeholder 的 left/top/width/height/font_size/color/align/line_count。"
        "只有当 bbox 明显漏字、包进图形、颜色或字号明显不准时，才允许做小幅微调。"
        "创建ppt，只需要文字部分。"
        "按占位框位置创建文本框并输入文字。"
        "要求文本属性一致，文字背景无填充。"
        "根据我的要求创建.pptx文件。"
        "不要参考任何流程、任何其他文件，只根据 text_placeholders 和这两张图肉眼可见的信息生成单页 page_script。"
        "字号单位是 PowerPoint pt，请按最终 PPT 实际观感估算，不要为了醒目而故意放大。"
        "如果原稿图里是多条独立单行 bullet，就按单行分别创建，不要合并成一个大段文本框。"
        "编号徽标、短标签、芯片字样、底部长横幅标题都要单独成框，并尽量保持单行。"
        "短标题和卡片标题不要截断，也不要拆成逐字换行。"
        "只允许写原稿图里肉眼可见的真实文字，不要把代码图标、流程图图形、装饰符号、窗口按钮、芯片轮廓脑补成文字。"
        "像 </>、箭头、空白方框、流程线、窗口按钮等默认视为图形，不要额外生成文字，除非原稿图里明确存在真实文本。"
        "元素图只用于帮助你判断文字与图形的相对关系，输出时仍然只写文字框，不要写背景、边框、图标、箭头、装饰线，也不要调用 add_assets。元素会在导出时单独加入。"
        "坐标单位必须是像素，基于给定画布。"
        "优先使用 add_text / add_center_text / add_runs，不要使用 add_text_ref / add_center_text_ref。"
        "允许的调用只有："
        'add_text(slide, "文字", x, y, w, h, size=12, color="163A63", bold=False, align="LEFT", anchor="TOP")；'
        'add_center_text(slide, "文字", x, y, w, h, size=12, color="163A63", bold=False, anchor="MIDDLE")；'
        'add_runs(slide, [{"text":"前半句","size":18,"color":"163A63","bold":True},{"text":"后半句","size":18,"color":"EE3D47","bold":True}], x, y, w, h, align="LEFT", anchor="TOP")。'
        '输出必须是严格 JSON，格式为 {"page_script":"..."}。'
        "page_script 中只能包含以上函数调用、空行和以 # 开头的注释。"
        f"\n页面信息：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_direct_page_refine_prompt(
    *,
    image_width: int,
    image_height: int,
    page_script: str,
    asset_adjustments: dict[str, Any],
    round_index: int,
) -> str:
    """构建基于真实 PPT 渲染图的单页文字修正提示词。"""
    payload = {
        "canvas": {"width": int(image_width), "height": int(image_height)},
        "refine_round": int(round_index) + 1,
        "current_page_script": str(page_script),
    }
    return (
        "第一张图是完整原稿图，第二张图是当前 PPT 的真实导出渲染图。"
        "请直接修正 page_script，让第二张图尽量贴近第一张图。"
        "重点检查：字号、位置、宽高、对齐、换行、是否压线、是否偏离元素中心、文本是否过大或过小。"
        "本轮只修文字，不要修改元素贴图位置与尺寸；元素位置沿用前置资产拟合对齐结果。"
        "不要输出新的图形、背景或边框。"
        "如果原稿图里是多条独立单行 bullet，就按单行分别保留，不要合并成一个大段文本框。"
        "编号徽标、短标签、芯片字样、底部长横幅标题都要单独成框，并尽量保持单行。"
        "只允许写原稿图里肉眼可见的真实文字，不要把图标、流程图轮廓、装饰符号、窗口按钮脑补成文字。"
        "允许的文字调用只有 add_text / add_center_text / add_runs。"
        '输出必须是严格 JSON，格式为 {"page_script":"...","asset_adjustments":{...}}。'
        "asset_adjustments 固定返回空对象 {}。"
        "返回完整 page_script 和完整 asset_adjustments，不要只返回 diff。"
        f"\n页面信息：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_direct_page_preview_project(
    *,
    reference_image: Path,
    elements_image: Path,
    image_width: int,
    image_height: int,
    slide_width_inch: float,
    page_no: int,
) -> dict[str, Any]:
    """构建页级预览项目，供主链生成预览脚本复用。"""
    return {
        "slide_width_inch": float(slide_width_inch),
        "image_width": int(image_width),
        "image_height": int(image_height),
        "default_font": {
            "font_name": DEFAULT_FONT_NAME,
            "font_size": 20,
            "color": DEFAULT_FONT_COLOR,
            "bold": False,
            "align": "LEFT",
        },
        "pages": [
            {
                "page_no": int(page_no),
                "title": "",
                "summary": "",
                "visual_image": str(elements_image.resolve()),
                "reference_image": str(reference_image.resolve()),
                "texts": [],
            }
        ],
    }


def prepare_direct_page_assets(
    *,
    work_dir: Path,
    page_no: int,
    elements_image: Path,
    reference_image: Path | None = None,
    reference_text_boxes: list[tuple[int, int, int, int]] | None = None,
    image_width: int,
    image_height: int,
    alpha_threshold: int = 8,
    min_area: int = 8,
    min_width: int = 0,
    min_height: int = 0,
    padding: int = 0,
    merge_distance: int = 6,
    skip_enhance: bool = False,
    skip_transparent: bool = False,
    preserve_existing_transparency: bool = True,
    preserve_tiny_components: bool | None = None,
    cleanup_intermediate_images: bool = True,
    stop_checker: StopChecker | None = None,
) -> PreparedDirectPageAssets:
    """把元素图处理成分割后的 PNG 资产，供生成脚本与文字框叠加。"""
    _ensure_not_stopped(stop_checker)
    page_dir = work_dir / f"page_{int(page_no):02d}"
    assets_dir = page_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    current_source = Path(elements_image)
    transparent_preview_image: Path | None = None
    alpha_profile = inspect_image_alpha(current_source)
    transparent_input = bool(preserve_existing_transparency) and bool(alpha_profile.has_transparency)
    resolved_skip_enhance = bool(skip_enhance) or transparent_input
    resolved_skip_transparent = bool(skip_transparent) or transparent_input
    resolved_preserve_tiny_components = (
        transparent_input if preserve_tiny_components is None else bool(preserve_tiny_components)
    )
    resolved_min_area = 1 if resolved_preserve_tiny_components else int(min_area)

    if not resolved_skip_enhance:
        enhanced_path = page_dir / f"page_{int(page_no):02d}_enhanced.png"
        enhance_image(current_source, enhanced_path)
        current_source = enhanced_path
    _ensure_not_stopped(stop_checker)

    if not resolved_skip_transparent:
        transparent_path = page_dir / f"page_{int(page_no):02d}_transparent.png"
        make_transparent(current_source, transparent_path)
        current_source = transparent_path
        transparent_preview_image = page_dir / f"page_{int(page_no):02d}_transparent_preview.png"
        shutil.copyfile(transparent_path, transparent_preview_image)
    elif transparent_input:
        transparent_preview_image = current_source
    _ensure_not_stopped(stop_checker)

    alignment_decision = None
    if reference_image is not None:
        aligned_path = page_dir / f"page_{int(page_no):02d}_aligned_for_split.png"
        alignment_decision = align_elements_image_to_reference(
            reference_image=Path(reference_image),
            elements_image=current_source,
            output_path=aligned_path,
            text_boxes=list(reference_text_boxes or []),
            alpha_threshold=int(alpha_threshold),
        )
    _ensure_not_stopped(stop_checker)

    manifest = split_transparent_png(
        current_source,
        assets_dir,
        alpha_threshold=int(alpha_threshold),
        min_area=int(resolved_min_area),
        min_width=int(min_width),
        min_height=int(min_height),
        padding=int(padding),
        merge_distance=int(merge_distance),
    )
    if int(manifest.get("count", 0)) <= 0:
        raise RuntimeError(f"第 {page_no} 页元素分割结果为空，无法继续导出。")
    _ensure_not_stopped(stop_checker)
    removed_intermediate_images: list[str] = []
    if bool(cleanup_intermediate_images):
        removed_intermediate_images = cleanup_split_intermediate_images(page_dir, page_no=page_no)
    _ensure_not_stopped(stop_checker)
    manifest_path = assets_dir / "assets.json"
    global_alignment = None
    asset_adjustments: dict[str, Any] = {}
    if alignment_decision is not None:
        global_alignment = {
            "should_apply": bool(alignment_decision.should_apply),
            "dx": int(alignment_decision.dx),
            "dy": int(alignment_decision.dy),
            "baseline_iou": float(alignment_decision.baseline_iou),
            "shifted_iou": float(alignment_decision.shifted_iou),
            "confidence": float(alignment_decision.confidence),
            "reason": alignment_decision.reason,
        }
        if bool(alignment_decision.should_apply) and (int(alignment_decision.dx) or int(alignment_decision.dy)):
            asset_adjustments = {
                "global": {
                    "dx": int(alignment_decision.dx),
                    "dy": int(alignment_decision.dy),
                }
            }
    return PreparedDirectPageAssets(
        manifest_path=str(manifest_path),
        manifest=manifest,
        image_width=int(image_width),
        image_height=int(image_height),
        split_source_image=str(current_source),
        transparent_preview_image=str(transparent_preview_image) if transparent_preview_image else None,
        removed_intermediate_images=removed_intermediate_images,
        global_alignment=global_alignment,
        asset_adjustments=asset_adjustments,
    )


def render_direct_comparison_image(reference_image: Path, preview_image: Path, output_path: Path) -> Path:
    """导出原稿图与真实 PPT 渲染图的并排对照，便于快速检查效果。"""
    reference = Image.open(reference_image).convert("RGBA")
    preview = Image.open(preview_image).convert("RGBA")
    title_height = 64
    canvas = Image.new(
        "RGBA",
        (reference.width + preview.width, max(reference.height, preview.height) + title_height),
        (255, 255, 255, 255),
    )
    canvas.alpha_composite(reference, (0, title_height))
    canvas.alpha_composite(preview, (reference.width, title_height))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)
    return output_path


def _write_page_preview_script(
    *,
    project: dict[str, Any],
    work_dir: Path,
    output_pptx: Path,
    page_no: int,
    page_script: str,
    script_path: Path,
) -> Path:
    """把当前 page_script 写成可执行的单页脚本文件。"""
    script_source = build_project_script_source(
        project,
        work_dir,
        output_pptx,
        [
            {
                "page_no": int(page_no),
                "script": str(page_script),
                "asset_adjustments": project.get("asset_adjustments", {}).get(str(int(page_no)), {}),
            }
        ],
        include_assets=True,
        layer_mode=OVERLAY_LAYER_MODE,
    )
    script_path.write_text(script_source, encoding="utf-8")
    return script_path


def _generate_page_script_from_images(
    provider: OpenAIChatProvider,
    *,
    reference_image: Path,
    elements_image: Path,
    image_width: int,
    image_height: int,
    text_placeholders: dict[str, Any] | None = None,
    stop_checker: StopChecker | None = None,
) -> str:
    """首轮基于原稿图和元素图请求模型生成单页文字脚本。"""
    prompt = build_direct_page_prompt(
        image_width=image_width,
        image_height=image_height,
        text_placeholders=text_placeholders,
    )
    messages = [
        {
            "role": "system",
            "content": "你是 PPT 单页文字直出助手。你只根据图片生成可执行 page_script，只输出 JSON。",
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                provider.build_image_message_item(reference_image),
                provider.build_image_message_item(elements_image),
            ],
        },
    ]
    result = run_interruptible_call(
        lambda: provider.complete_json(messages),
        stop_checker=stop_checker,
        interruption_message="首轮文字脚本模型请求已被中断",
    )
    raw_script = str(result.get("page_script", "")).strip()
    if not raw_script:
        raise RuntimeError("模型没有返回可执行 page_script。")
    return normalize_page_script(raw_script)


def _revise_page_script_with_rendered_preview(
    provider: OpenAIChatProvider,
    *,
    reference_image: Path,
    rendered_preview: Path,
    image_width: int,
    image_height: int,
    page_script: str,
    asset_adjustments: dict[str, Any],
    round_index: int,
    stop_checker: StopChecker | None = None,
) -> DirectPageScriptRevision:
    """基于真实 PPT 渲染图请求模型修正单页文字脚本。"""
    prompt = build_direct_page_refine_prompt(
        image_width=image_width,
        image_height=image_height,
        page_script=page_script,
        asset_adjustments=asset_adjustments,
        round_index=round_index,
    )
    messages = [
        {
            "role": "system",
            "content": "你是 PPT 单页文字修正助手。你根据原稿图与真实导出图只修正 page_script，asset_adjustments 必须返回空对象，只输出 JSON。",
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                provider.build_image_message_item(reference_image),
                provider.build_image_message_item(rendered_preview),
            ],
        },
    ]
    result = run_interruptible_call(
        lambda: provider.complete_json(messages),
        stop_checker=stop_checker,
        interruption_message="文字脚本回看修正模型请求已被中断",
    )
    raw_script = str(result.get("page_script", "")).strip()
    resolved_script = normalize_page_script(raw_script) if raw_script else page_script
    resolved_adjustments = normalize_asset_adjustments(asset_adjustments)
    return DirectPageScriptRevision(
        page_script=resolved_script,
        asset_adjustments=resolved_adjustments,
    )
