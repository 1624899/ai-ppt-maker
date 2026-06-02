from __future__ import annotations

import re
import uuid
import json
from pathlib import Path
from typing import Any, Sequence

from PIL import Image, ImageColor, ImageOps

from ppt_system.export.delivery_options import REFERENCE_PPT_FILENAME, build_editable_ppt_filename
from ppt_system.export.export_layer_mode import SEPARATE_LAYER_MODE
from ppt_system.generation.generation_prompts import build_elements_prompt
from ppt_system.jobs.job_targets import JOB_TARGET_EDITABLE_PPT, JOB_TARGET_REFERENCE_ONLY
from ppt_system.web.services.job_submission_runtime import build_active_config


DEFAULT_REFERENCE_PROMPT = "外部导入原稿图，跳过一阶段原稿图生成，直接继续元素图和可编辑 PPT 转换。"
EXTERNAL_REFERENCE_SOURCE_MODE = "external_reference"
RESIZE_MODES = {"stretch", "contain", "cover"}
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def natural_sort_key(path: Path) -> list[Any]:
    """按人类习惯排序图片文件名，避免 page_10 排到 page_2 前面。"""
    parts: list[Any] = []
    for part in re.split(r"(\d+)", path.name.lower()):
        parts.append(int(part) if part.isdigit() else part)
    return parts


def collect_reference_images(root: Path, reference_path: Path, *, recursive: bool = False) -> list[Path]:
    """从单图或文件夹收集可作为原稿图的图片。"""
    resolved_path = reference_path.expanduser()
    if not resolved_path.is_absolute():
        resolved_path = root / resolved_path
    resolved_path = resolved_path.resolve()

    if resolved_path.is_file():
        if resolved_path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
            raise ValueError(f"不支持的图片格式：{resolved_path.suffix}")
        return [resolved_path]
    if not resolved_path.exists():
        raise FileNotFoundError(f"外部原稿图路径不存在：{resolved_path}")
    if not resolved_path.is_dir():
        raise ValueError(f"外部原稿图路径既不是文件也不是文件夹：{resolved_path}")

    iterator = resolved_path.rglob("*") if recursive else resolved_path.iterdir()
    images = [
        item.resolve()
        for item in iterator
        if item.is_file() and item.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES
    ]
    images.sort(key=natural_sort_key)
    if not images:
        suffixes = "、".join(sorted(SUPPORTED_IMAGE_SUFFIXES))
        raise ValueError(f"文件夹中没有可用图片：{resolved_path}；支持格式：{suffixes}")
    return images


def normalize_resize_mode(value: Any) -> str:
    mode = str(value or "stretch").strip().lower()
    if mode not in RESIZE_MODES:
        raise ValueError(f"图片适配方式只能是：{', '.join(sorted(RESIZE_MODES))}")
    return mode


def normalize_reference_image(
    source_path: Path,
    output_path: Path,
    *,
    target_width: int,
    target_height: int,
    resize_mode: str,
    background: str,
) -> None:
    """把任意外部图片规范成后续流水线使用的固定画布。"""
    resolved_mode = normalize_resize_mode(resize_mode)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    background_rgba = ImageColor.getcolor(str(background or "#FFFFFF"), "RGBA")

    with Image.open(source_path) as raw_image:
        image = raw_image.convert("RGBA")
        if resolved_mode == "stretch":
            normalized = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
        elif resolved_mode == "cover":
            normalized = ImageOps.fit(
                image,
                (target_width, target_height),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
        else:
            normalized = Image.new("RGBA", (target_width, target_height), background_rgba)
            contained = ImageOps.contain(image, (target_width, target_height), method=Image.Resampling.LANCZOS)
            left = (target_width - contained.width) // 2
            top = (target_height - contained.height) // 2
            normalized.alpha_composite(contained, (left, top))

        flattened = Image.new("RGBA", normalized.size, background_rgba)
        flattened.alpha_composite(normalized)
        flattened.convert("RGB").save(output_path)


def build_external_page(
    *,
    page_no: int,
    page_title: str,
    reference_prompt: str,
    elements_prompt: str,
    reference_url: str,
) -> dict[str, Any]:
    return {
        "page_no": int(page_no),
        "title": page_title,
        "summary": "由外部原稿图继续转换。",
        "bullets": [],
        "layout_intent": "external_reference_resume",
        "layout_family": "grid_n_x_m",
        "page_richness": "medium",
        "element_plan": {},
        "reference_mode": EXTERNAL_REFERENCE_SOURCE_MODE,
        "prompt_profile": "external",
        "status": "reference_done",
        "reference_image": reference_url,
        "element_image": "",
        "reference_prompt": reference_prompt,
        "elements_prompt": elements_prompt,
        "layout_slots": [],
        "texts": [],
    }


def mark_stage(
    state: dict[str, Any],
    stage_key: str,
    *,
    status: str,
    summary: str,
    logs: list[str] | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    for stage in state.get("stages", []):
        if stage.get("key") != stage_key:
            continue
        stage["status"] = status
        stage["summary"] = summary
        if logs is not None:
            stage["logs"] = logs
        if data is not None:
            stage["data"] = data
        return


def build_initial_state(
    runtime: Any,
    *,
    job_id: str,
    content: str,
    image_preset: dict[str, Any],
    image_quality: str,
    generation_options: dict[str, Any],
    pages: list[dict[str, Any]],
    reference_items: list[dict[str, Any]],
    job_target: str,
    create_only: bool,
) -> dict[str, Any]:
    state = runtime.build_job_state(
        job_id,
        content,
        len(pages),
        image_preset,
        image_quality,
        "",
        generation_options,
        [],
        job_target,
    )
    state["plan"] = {
        "style_type": EXTERNAL_REFERENCE_SOURCE_MODE,
        "audience": "",
        "narrative": "外部原稿图续跑",
        "style_guide": {},
        "image_preset": image_preset,
        "style_notes": "",
        "generation_options": generation_options,
        "pages": [
            {
                "page_no": page["page_no"],
                "title": page["title"],
                "summary": page["summary"],
                "bullets": page["bullets"],
                "layout_intent": page["layout_intent"],
                "layout_family": page["layout_family"],
                "page_richness": page["page_richness"],
                "element_plan": page["element_plan"],
                "reference_mode": page["reference_mode"],
                "prompt_profile": page["prompt_profile"],
                "image_prompt": page["reference_prompt"],
            }
            for page in pages
        ],
    }
    state["pages"] = pages
    state["reference_pages"] = reference_items
    state["element_pages"] = []
    state["job_meta"]["source_mode"] = EXTERNAL_REFERENCE_SOURCE_MODE
    state["job_meta"]["source_mode_label"] = "已有原稿图导入"

    mark_stage(
        state,
        "planning",
        status="completed",
        summary=f"已由外部原稿图构建 {len(pages)} 页任务规划",
        logs=[f"跳过模型规划：使用外部原稿图创建 {len(pages)} 页续跑任务。"],
        data={"pages": state["plan"]["pages"]},
    )
    mark_stage(
        state,
        "reference_generation",
        status="completed",
        summary=f"已登记 {len(reference_items)} 张外部原稿图",
        logs=["跳过原稿图生成：外部图片已复制并规范到任务原稿图目录。"],
        data={"pages": reference_items},
    )
    if create_only:
        state["status"] = "completed"
        state["current_stage"] = "reference_generation"
        mark_stage(
            state,
            "elements_generation",
            status="skipped",
            summary="任务已停在原稿图完成状态，可继续生成可编辑元素",
        )
        mark_stage(
            state,
            "ppt_export",
            status="skipped",
            summary="任务已停在原稿图完成状态，可继续导出",
        )
    else:
        state["status"] = "queued"
        state["current_stage"] = "queued"
    return state


def create_reference_only_delivery(
    runtime: Any,
    *,
    job_id: str,
    job_dir: Path,
    state: dict[str, Any],
    image_width: int,
    image_height: int,
) -> dict[str, Any]:
    output_pptx = job_dir / REFERENCE_PPT_FILENAME
    preview_export = runtime.export_reference_images_to_pptx(
        state["reference_pages"],
        job_dir,
        output_pptx,
        image_width=image_width,
        image_height=image_height,
    )
    delivery = runtime.build_reference_delivery_payload(
        job_id,
        job_dir,
        output_pptx,
        page_count=int(preview_export["page_count"]),
        logical_page_count=len(state["reference_pages"]),
    )
    return runtime.set_reference_delivery(runtime.normalize_job_result_payload({}), delivery)


def create_external_reference_job(
    runtime: Any,
    *,
    config: dict[str, Any],
    source_images: Sequence[Path],
    job_id: str = "",
    title: str = "",
    content: str = "",
    page_title: str = "",
    image_preset_name: str = "",
    image_quality: str = "",
    resize_mode: str = "stretch",
    background: str = "#FFFFFF",
    create_only: bool = False,
) -> dict[str, Any]:
    """创建“已有原稿图导入”任务，必要时停在原稿图完成态。"""
    normalized_sources = [Path(path).resolve() for path in source_images]
    if not normalized_sources:
        raise ValueError("请至少提供一张外部原稿图。")
    page_count = len(normalized_sources)
    max_pages = int(config.get("max_pages") or 0)
    if max_pages > 0 and page_count > max_pages:
        raise ValueError(f"导入原稿图数量不能超过 {max_pages} 张。")

    resolved_resize_mode = normalize_resize_mode(resize_mode)
    preset_name = str(image_preset_name or config.get("default_image_preset", "landscape_2k"))
    image_preset = runtime.resolve_image_preset(config, preset_name)
    resolved_quality = str(image_quality or config.get("image_quality", "medium")).strip().lower()
    if resolved_quality not in {"low", "medium", "high", "auto"}:
        raise ValueError("图像质量只能选择 low、medium、high 或 auto。")
    active_config = build_active_config(config, image_preset, resolved_quality)
    generation_options = runtime.resolve_generation_options({"page_count": page_count}, config=config)

    resolved_job_id = str(job_id or uuid.uuid4().hex[:12]).strip()
    if not resolved_job_id:
        raise ValueError("任务 ID 不能为空。")
    if runtime.get_job_record(runtime.JOBS_DB_PATH, resolved_job_id):
        raise ValueError(f"任务已存在：{resolved_job_id}")

    job_dir = runtime.ROOT / str(config.get("output_dir", "output")) / resolved_job_id
    refs_dir = job_dir / "style_refs"
    stage1_dir = job_dir / "01_reference_pages"
    stage2_dir = job_dir / "02_elements_pages"
    refs_dir.mkdir(parents=True, exist_ok=True)
    stage1_dir.mkdir(parents=True, exist_ok=True)
    stage2_dir.mkdir(parents=True, exist_ok=True)

    image_width = int(active_config["image_width"])
    image_height = int(active_config["image_height"])
    reference_prompt = DEFAULT_REFERENCE_PROMPT
    elements_prompt = build_elements_prompt()
    pages: list[dict[str, Any]] = []
    reference_items: list[dict[str, Any]] = []
    reference_paths: list[Path] = []
    for page_no, source_image in enumerate(normalized_sources, start=1):
        reference_path = stage1_dir / f"page_{page_no:02d}_reference.png"
        normalize_reference_image(
            source_image,
            reference_path,
            target_width=image_width,
            target_height=image_height,
            resize_mode=resolved_resize_mode,
            background=background,
        )
        reference_paths.append(reference_path)

        if page_title and page_count == 1:
            resolved_page_title = str(page_title).strip()
        elif page_title:
            resolved_page_title = f"{str(page_title).strip()} {page_no:02d}"
        else:
            resolved_page_title = source_image.stem
        reference_url = f"/runs/{resolved_job_id}/01_reference_pages/{reference_path.name}"
        reference_item = {
            "page_no": page_no,
            "title": resolved_page_title,
            "prompt": reference_prompt,
            "image": reference_url,
            "generation": {
                "provider": "external_reference_image",
                "source_image": str(source_image),
                "normalized_size": f"{image_width}x{image_height}",
                "resize_mode": resolved_resize_mode,
            },
        }
        reference_items.append(reference_item)
        pages.append(
            build_external_page(
                page_no=page_no,
                page_title=resolved_page_title,
                reference_prompt=reference_prompt,
                elements_prompt=elements_prompt,
                reference_url=reference_url,
            )
        )

    if content:
        resolved_content = str(content).strip()
    elif page_count == 1:
        resolved_content = f"外部原稿图续跑：{normalized_sources[0].name}"
    else:
        source_parent = normalized_sources[0].parent
        resolved_content = f"外部原稿图文件夹续跑：{source_parent.name}（共 {page_count} 张）"

    job_target = JOB_TARGET_REFERENCE_ONLY if create_only else JOB_TARGET_EDITABLE_PPT
    state = build_initial_state(
        runtime,
        job_id=resolved_job_id,
        content=resolved_content,
        image_preset=image_preset,
        image_quality=resolved_quality,
        generation_options=generation_options,
        pages=pages,
        reference_items=reference_items,
        job_target=job_target,
        create_only=create_only,
    )

    result_payload = runtime.normalize_job_result_payload({})
    if create_only:
        result_payload = create_reference_only_delivery(
            runtime,
            job_id=resolved_job_id,
            job_dir=job_dir,
            state=state,
            image_width=image_width,
            image_height=image_height,
        )
        state["result"] = result_payload

    request_payload = {
        "content": resolved_content,
        "page_count": page_count,
        "image_preset": preset_name,
        "image_quality": resolved_quality,
        "style_notes": "",
        "job_target": job_target,
        "workflow_mode": "auto",
        "generation_options": generation_options,
        "include_cover_page": generation_options["include_cover_page"],
        "page_richness_default": generation_options["page_richness_default"],
        "page_richness_map": generation_options["page_richness_map"],
        "reference_style_adherence": generation_options["reference_style_adherence"],
        "style_reference_images": [],
        "source_mode": EXTERNAL_REFERENCE_SOURCE_MODE,
        "source_mode_label": "已有原稿图导入",
        "external_reference_images": [str(source_image) for source_image in normalized_sources],
        "external_reference_resize_mode": resolved_resize_mode,
        "external_reference_background": str(background or "#FFFFFF"),
        "external_reference_create_only": bool(create_only),
    }
    runtime.create_job_record(
        runtime.JOBS_DB_PATH,
        {
            "job_id": resolved_job_id,
            "status": state["status"],
            "current_stage": state["current_stage"],
            "title": str(title or runtime.build_job_title(resolved_content)),
            "content": resolved_content,
            "page_count": page_count,
            "image_preset": preset_name,
            "image_quality": resolved_quality,
            "style_notes": "",
            "job_dir": str(job_dir),
            "request": request_payload,
            "state": state,
            "result": result_payload,
            "stop_requested": False,
        },
    )
    runtime.save_job_state(job_dir, state)
    (job_dir / "config.snapshot.json").write_text(
        json.dumps(active_config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "job_id": resolved_job_id,
        "job_dir": job_dir,
        "config": config,
        "active_config": active_config,
        "image_preset": image_preset,
        "image_preset_name": preset_name,
        "image_quality": resolved_quality,
        "generation_options": generation_options,
        "content": resolved_content,
        "refs_dir": refs_dir,
        "stage1_dir": stage1_dir,
        "stage2_dir": stage2_dir,
        "reference_path": reference_paths[0],
        "reference_paths": reference_paths,
        "page_count": page_count,
        "request_payload": request_payload,
        "state": state,
        "result_payload": result_payload,
        "output_pptx": job_dir / build_editable_ppt_filename(SEPARATE_LAYER_MODE),
    }
