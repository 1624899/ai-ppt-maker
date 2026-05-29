from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from ppt_system.export_layer_mode import OVERLAY_LAYER_MODE
from ppt_system.global_element_alignment import align_elements_image_to_reference
from ppt_system.image_ops import enhance_image, make_transparent
from ppt_system.intermediate_artifact_cleanup import cleanup_split_intermediate_images
from ppt_system.openai_chat_provider import OpenAIChatProvider
from ppt_system.ppt_calibration_renderer import render_pptx_first_slide_to_png
from ppt_system.splitter import split_transparent_png
from ppt_system.text_script_runtime import (
    build_project_script_source,
    execute_generated_text_script,
    normalize_asset_adjustments,
    normalize_page_script,
)
from ppt_system.text_placeholder_detection import placeholder_bboxes, save_text_placeholders


DEFAULT_SLIDE_WIDTH_INCH = 13.333333
DEFAULT_FONT_NAME = "Microsoft YaHei"
DEFAULT_FONT_COLOR = "355C7D"


@dataclass
class DirectPageGenerationMetadata:
    office_render_available: bool = False
    refine_rounds_applied: int = 0
    office_preview_paths: list[str] | None = None
    comparison_paths: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "office_render_available": bool(self.office_render_available),
            "refine_rounds_applied": int(self.refine_rounds_applied),
            "office_preview_paths": list(self.office_preview_paths or []),
            "comparison_paths": list(self.comparison_paths or []),
        }


@dataclass
class DirectPageRefineResult:
    page_script: str
    asset_adjustments: dict[str, Any]


@dataclass(frozen=True)
class PreparedDirectPageAssets:
    manifest_path: str
    manifest: dict[str, Any]
    image_width: int
    image_height: int
    split_source_image: str
    removed_intermediate_images: list[str]
    global_alignment: dict[str, Any] | None
    asset_adjustments: dict[str, Any]


def normalize_output_pptx_name(output_name: str) -> str:
    """统一补全导出文件后缀，避免生成无扩展名文件。"""
    resolved = str(output_name or "").strip() or "result.pptx"
    if Path(resolved).suffix.lower() == ".pptx":
        return resolved
    return f"{resolved}.pptx"


def resolve_canvas_size(reference_image: Path, elements_image: Path) -> tuple[int, int]:
    """优先读取参考图尺寸，失败时退回元素图。"""
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
    """构建首轮依赖参考图和元素图的单页脚本提示词。"""
    payload = {
        "canvas": {"width": int(image_width), "height": int(image_height)},
        "task": "single_page_text_only",
        "text_placeholders": []
        if not isinstance(text_placeholders, dict)
        else list(text_placeholders.get("placeholders", [])),
    }
    return (
        "第一张图是完整参考图，第二张图是去文字后的元素图。"
        "系统已用 OpenCV 根据“参考图 - 去文字元素图”估计出 text_placeholders。"
        "你的首要任务是识别并填写每个 placeholder 对应的真实文字内容。"
        "默认沿用 placeholder 的 left/top/width/height/font_size/color/align/line_count。"
        "只有当 bbox 明显漏字、包进图形、颜色或字号明显不准时，才允许做小幅微调。"
        "创建ppt，只需要文字部分。"
        "按占位框位置创建文本框并输入文字。"
        "要求文本属性一致，文字背景无填充。"
        "根据我的要求创建.pptx文件。"
        "不要参考任何流程、任何其他文件，只根据 text_placeholders 和这两张图肉眼可见的信息生成单页 page_script。"
        "字号单位是 PowerPoint pt，请按最终 PPT 实际观感估算，不要为了醒目而故意放大。"
        "如果参考图里是多条独立单行 bullet，就按单行分别创建，不要合并成一个大段文本框。"
        "编号徽标、短标签、芯片字样、底部长横幅标题都要单独成框，并尽量保持单行。"
        "短标题和卡片标题不要截断，也不要拆成逐字换行。"
        "只允许写参考图里肉眼可见的真实文字，不要把代码图标、流程图图形、装饰符号、窗口按钮、芯片轮廓脑补成文字。"
        "像 </>、箭头、空白方框、流程线、窗口按钮等默认视为图形，不要额外生成文字，除非参考图里明确存在真实文本。"
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
        "第一张图是完整参考图，第二张图是当前 PPT 的真实导出渲染图。"
        "请直接修正 page_script，让第二张图尽量贴近第一张图。"
        "重点检查：字号、位置、宽高、对齐、换行、是否压线、是否偏离元素中心、文本是否过大或过小。"
        "本轮只修文字，不要修改元素贴图位置与尺寸；元素位置沿用前置资产拟合对齐结果。"
        "不要输出新的图形、背景或边框。"
        "如果参考图里是多条独立单行 bullet，就按单行分别保留，不要合并成一个大段文本框。"
        "编号徽标、短标签、芯片字样、底部长横幅标题都要单独成框，并尽量保持单行。"
        "只允许写参考图里肉眼可见的真实文字，不要把图标、流程图轮廓、装饰符号、窗口按钮脑补成文字。"
        "允许的文字调用只有 add_text / add_center_text / add_runs。"
        '输出必须是严格 JSON，格式为 {"page_script":"...","asset_adjustments":{...}}。'
        "asset_adjustments 固定返回空对象 {}。"
        "返回完整 page_script 和完整 asset_adjustments，不要只返回 diff。"
        f"\n页面信息：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_direct_single_page_project(
    *,
    reference_image: Path,
    elements_image: Path,
    image_width: int,
    image_height: int,
    slide_width_inch: float,
    page_no: int,
) -> dict[str, Any]:
    """构建最小单页项目，供脚本模板复用。"""
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
    cleanup_intermediate_images: bool = True,
) -> PreparedDirectPageAssets:
    """把元素图处理成分割后的 PNG 资产，供生成脚本与文字框叠加。"""
    page_dir = work_dir / f"page_{int(page_no):02d}"
    assets_dir = page_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    current_source = Path(elements_image)

    if not bool(skip_enhance):
        enhanced_path = page_dir / f"page_{int(page_no):02d}_enhanced.png"
        enhance_image(current_source, enhanced_path)
        current_source = enhanced_path

    if not bool(skip_transparent):
        transparent_path = page_dir / f"page_{int(page_no):02d}_transparent.png"
        make_transparent(current_source, transparent_path)
        current_source = transparent_path

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

    manifest = split_transparent_png(
        current_source,
        assets_dir,
        alpha_threshold=int(alpha_threshold),
        min_area=int(min_area),
        min_width=int(min_width),
        min_height=int(min_height),
        padding=int(padding),
        merge_distance=int(merge_distance),
    )
    if int(manifest.get("count", 0)) <= 0:
        raise RuntimeError(f"第 {page_no} 页元素分割结果为空，无法继续导出。")
    removed_intermediate_images: list[str] = []
    if bool(cleanup_intermediate_images):
        removed_intermediate_images = cleanup_split_intermediate_images(page_dir, page_no=page_no)
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
        removed_intermediate_images=removed_intermediate_images,
        global_alignment=global_alignment,
        asset_adjustments=asset_adjustments,
    )


def render_direct_comparison_image(reference_image: Path, preview_image: Path, output_path: Path) -> Path:
    """导出参考图与真实 PPT 渲染图的并排对照，便于快速检查效果。"""
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


def _write_direct_page_script(
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


def _request_direct_page_script(
    provider: OpenAIChatProvider,
    *,
    reference_image: Path,
    elements_image: Path,
    image_width: int,
    image_height: int,
    text_placeholders: dict[str, Any] | None = None,
) -> str:
    """首轮基于参考图和元素图请求模型生成单页文字脚本。"""
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
    result = provider.complete_json(messages)
    raw_script = str(result.get("page_script", "")).strip()
    if not raw_script:
        raise RuntimeError("模型没有返回可执行 page_script。")
    return normalize_page_script(raw_script)


def _refine_direct_page_script(
    provider: OpenAIChatProvider,
    *,
    reference_image: Path,
    rendered_preview: Path,
    image_width: int,
    image_height: int,
    page_script: str,
    asset_adjustments: dict[str, Any],
    round_index: int,
) -> DirectPageRefineResult:
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
            "content": "你是 PPT 单页文字修正助手。你根据参考图与真实导出图只修正 page_script，asset_adjustments 必须返回空对象，只输出 JSON。",
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
    result = provider.complete_json(messages)
    raw_script = str(result.get("page_script", "")).strip()
    resolved_script = normalize_page_script(raw_script) if raw_script else page_script
    resolved_adjustments = normalize_asset_adjustments(asset_adjustments)
    return DirectPageRefineResult(
        page_script=resolved_script,
        asset_adjustments=resolved_adjustments,
    )


def _generate_direct_single_page_script_with_metadata(
    provider: OpenAIChatProvider,
    reference_image: Path,
    elements_image: Path,
    work_dir: Path,
    output_pptx: Path,
    *,
    slide_width_inch: float = DEFAULT_SLIDE_WIDTH_INCH,
    page_no: int = 1,
    refine_rounds: int = 1,
) -> tuple[Path, DirectPageGenerationMetadata]:
    """生成单页文字脚本，并在可用时走真实 PPT 渲染闭环。"""
    resolved_reference = Path(reference_image)
    resolved_elements = Path(elements_image)
    if not resolved_reference.exists():
        raise FileNotFoundError(f"缺少参考图：{resolved_reference}")
    if not resolved_elements.exists():
        raise FileNotFoundError(f"缺少元素图：{resolved_elements}")

    work_dir.mkdir(parents=True, exist_ok=True)
    image_width, image_height = resolve_canvas_size(resolved_reference, resolved_elements)
    page_dir = work_dir / f"page_{int(page_no):02d}"
    text_placeholders = save_text_placeholders(
        resolved_reference,
        resolved_elements,
        page_dir / "text_placeholders.json",
        slide_width_inch=slide_width_inch,
    )
    asset_result = prepare_direct_page_assets(
        work_dir=work_dir,
        page_no=page_no,
        elements_image=resolved_elements,
        reference_image=resolved_reference,
        reference_text_boxes=placeholder_bboxes(text_placeholders),
        image_width=image_width,
        image_height=image_height,
    )
    project = build_direct_single_page_project(
        reference_image=resolved_reference,
        elements_image=resolved_elements,
        image_width=image_width,
        image_height=image_height,
        slide_width_inch=slide_width_inch,
        page_no=page_no,
    )
    current_asset_adjustments: dict[str, Any] = dict(asset_result.asset_adjustments)
    project["asset_adjustments"] = {str(int(page_no)): dict(current_asset_adjustments)}
    current_script = _request_direct_page_script(
        provider,
        reference_image=resolved_reference,
        elements_image=resolved_elements,
        image_width=image_width,
        image_height=image_height,
        text_placeholders=text_placeholders,
    )

    metadata = DirectPageGenerationMetadata(
        office_render_available=False,
        refine_rounds_applied=0,
        office_preview_paths=[],
        comparison_paths=[],
    )
    for round_index in range(max(0, int(refine_rounds))):
        preview_pptx = work_dir / f"render_preview_round_{round_index + 1:02d}.pptx"
        preview_script_path = work_dir / f"generated_text_layout_preview_round_{round_index + 1:02d}.py"
        _write_direct_page_script(
            project=project,
            work_dir=work_dir,
            output_pptx=preview_pptx,
            page_no=page_no,
            page_script=current_script,
            script_path=preview_script_path,
        )
        execute_generated_text_script(preview_script_path)

        preview_image_path = work_dir / f"office_preview_round_{round_index + 1:02d}.png"
        rendered_preview = render_pptx_first_slide_to_png(
            preview_pptx,
            preview_image_path,
            image_width=image_width,
            image_height=image_height,
        )
        if rendered_preview is None:
            break

        metadata.office_render_available = True
        metadata.office_preview_paths.append(str(rendered_preview))
        comparison_path = work_dir / f"comparison_round_{round_index + 1:02d}.png"
        render_direct_comparison_image(
            reference_image=resolved_reference,
            preview_image=rendered_preview,
            output_path=comparison_path,
        )
        metadata.comparison_paths.append(str(comparison_path))

        refine_result = _refine_direct_page_script(
            provider,
            reference_image=resolved_reference,
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
            break
        current_script = candidate_script
        current_asset_adjustments = candidate_adjustments
        project["asset_adjustments"] = {str(int(page_no)): dict(current_asset_adjustments)}
        metadata.refine_rounds_applied += 1

    script_path = work_dir / "generated_text_layout.py"
    project["asset_adjustments"] = {str(int(page_no)): dict(current_asset_adjustments)}
    _write_direct_page_script(
        project=project,
        work_dir=work_dir,
        output_pptx=output_pptx,
        page_no=page_no,
        page_script=current_script,
        script_path=script_path,
    )
    return script_path, metadata


def generate_direct_single_page_script(
    provider: OpenAIChatProvider,
    reference_image: Path,
    elements_image: Path,
    work_dir: Path,
    output_pptx: Path,
    *,
    slide_width_inch: float = DEFAULT_SLIDE_WIDTH_INCH,
    page_no: int = 1,
    refine_rounds: int = 1,
) -> Path:
    """生成单页文字脚本，并在可用时尝试真实 PPT 渲染回看。"""
    script_path, _ = _generate_direct_single_page_script_with_metadata(
        provider,
        reference_image,
        elements_image,
        work_dir,
        output_pptx,
        slide_width_inch=slide_width_inch,
        page_no=page_no,
        refine_rounds=refine_rounds,
    )
    return script_path


def generate_direct_single_page_ppt(
    provider: OpenAIChatProvider,
    reference_image: Path,
    elements_image: Path,
    work_dir: Path,
    output_pptx: Path,
    *,
    slide_width_inch: float = DEFAULT_SLIDE_WIDTH_INCH,
    page_no: int = 1,
    refine_rounds: int = 1,
) -> dict[str, Any]:
    """生成并执行单页脚本，直接得到 PPT。"""
    script_path, metadata = _generate_direct_single_page_script_with_metadata(
        provider,
        reference_image,
        elements_image,
        work_dir,
        output_pptx,
        slide_width_inch=slide_width_inch,
        page_no=page_no,
        refine_rounds=refine_rounds,
    )
    execute_generated_text_script(script_path)
    result: dict[str, Any] = {
        "output_pptx": str(output_pptx),
        "work_dir": str(work_dir),
        "text_script_path": str(script_path),
    }
    result.update(metadata.to_dict())
    return result
