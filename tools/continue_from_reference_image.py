from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from PIL import Image, ImageColor, ImageOps

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main as runtime  # noqa: E402
from ppt_system.export.delivery_options import (  # noqa: E402
    REFERENCE_PPT_FILENAME,
    build_editable_ppt_filename,
)
from ppt_system.export.export_layer_mode import SEPARATE_LAYER_MODE  # noqa: E402
from ppt_system.generation.generation_prompts import build_elements_prompt  # noqa: E402
from ppt_system.jobs.job_targets import (  # noqa: E402
    JOB_TARGET_EDITABLE_PPT,
    JOB_TARGET_REFERENCE_ONLY,
)
from ppt_system.runtime.console_encoding import configure_utf8_console  # noqa: E402
from ppt_system.web.services.job_submission_runtime import build_active_config  # noqa: E402


DEFAULT_REFERENCE_PATH = ROOT / "图片转换"
DEFAULT_REFERENCE_PROMPT = "外部导入原稿图，跳过一阶段原稿图生成，直接继续元素图和可编辑 PPT 转换。"
RESIZE_MODES = {"stretch", "contain", "cover"}
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="把已有图片登记为任务原稿图，并从元素图阶段继续转换。",
    )
    parser.add_argument(
        "reference_path",
        nargs="?",
        default=str(DEFAULT_REFERENCE_PATH),
        help="外部原稿图文件或文件夹；传文件夹时会把其中图片按文件名排序规划成多页任务。",
    )
    parser.add_argument("--job-id", default="", help="可选，自定义任务 ID；不传则自动生成。")
    parser.add_argument("--resume-job", default="", help="继续一个已创建的外部原稿图任务。")
    parser.add_argument("--title", default="", help="任务标题；不传则根据图片文件名生成。")
    parser.add_argument("--content", default="", help="任务内容摘要；不传则使用通用外部原稿图说明。")
    parser.add_argument("--page-title", default="", help="页面标题；仅用于任务元数据。")
    parser.add_argument(
        "--image-preset",
        default="",
        help="图像尺寸预设；不传则使用 config.json 的默认预设，当前默认是 2048x1152。",
    )
    parser.add_argument(
        "--image-quality",
        default="",
        choices=["", "low", "medium", "high", "auto"],
        help="元素图生成质量；不传则沿用 config.json。",
    )
    parser.add_argument(
        "--resize-mode",
        default="stretch",
        choices=sorted(RESIZE_MODES),
        help="外部原稿图转为目标画幅的方式：stretch 拉伸、contain 留白等比、cover 裁切等比。",
    )
    parser.add_argument("--background", default="#FFFFFF", help="contain 模式或透明图合成时使用的背景色。")
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="传入文件夹时递归收集子目录图片；默认只读取当前目录。",
    )
    parser.add_argument(
        "--create-only",
        action="store_true",
        help="只新建任务并停在原稿图完成状态，不立即调用模型继续转换。",
    )
    return parser.parse_args()


def natural_sort_key(path: Path) -> list[Any]:
    """按人类习惯排序图片文件名，避免 page_10 排到 page_2 前面。"""
    import re

    parts: list[Any] = []
    for part in re.split(r"(\d+)", path.name.lower()):
        if part.isdigit():
            parts.append(int(part))
        else:
            parts.append(part)
    return parts


def collect_reference_images(reference_path: Path, *, recursive: bool = False) -> list[Path]:
    """从单图或文件夹收集可作为原稿图的图片。"""
    resolved_path = reference_path.expanduser()
    if not resolved_path.is_absolute():
        resolved_path = ROOT / resolved_path
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
    if resize_mode not in RESIZE_MODES:
        raise ValueError(f"resize_mode 只能是：{', '.join(sorted(RESIZE_MODES))}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    background_rgba = ImageColor.getcolor(background, "RGBA")
    with Image.open(source_path) as raw_image:
        image = raw_image.convert("RGBA")
        if resize_mode == "stretch":
            normalized = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
        elif resize_mode == "cover":
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
        "reference_mode": "external_reference",
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
        "style_type": "external_reference",
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
            summary="任务已停在原稿图完成状态，可从界面继续生成可编辑元素",
        )
        mark_stage(
            state,
            "ppt_export",
            status="skipped",
            summary="任务已停在原稿图完成状态，可从界面继续导出",
        )
    else:
        state["status"] = "queued"
        state["current_stage"] = "queued"
    return state


def create_reference_only_delivery(
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


def create_external_reference_job(args: argparse.Namespace) -> dict[str, Any]:
    config = runtime.read_config()
    preset_name = str(args.image_preset or config.get("default_image_preset", "landscape_2k"))
    image_preset = runtime.resolve_image_preset(config, preset_name)
    image_quality = str(args.image_quality or config.get("image_quality", "medium")).strip().lower()
    active_config = build_active_config(config, image_preset, image_quality)
    source_images = collect_reference_images(Path(args.reference_path), recursive=bool(args.recursive))
    page_count = len(source_images)
    generation_options = runtime.resolve_generation_options({"page_count": page_count}, config=config)

    job_id = str(args.job_id or uuid.uuid4().hex[:12]).strip()
    if not job_id:
        raise ValueError("任务 ID 不能为空。")
    if runtime.get_job_record(runtime.JOBS_DB_PATH, job_id):
        raise ValueError(f"任务已存在：{job_id}")

    job_dir = ROOT / str(config.get("output_dir", "output")) / job_id
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
    for page_no, source_image in enumerate(source_images, start=1):
        reference_path = stage1_dir / f"page_{page_no:02d}_reference.png"
        normalize_reference_image(
            source_image,
            reference_path,
            target_width=image_width,
            target_height=image_height,
            resize_mode=str(args.resize_mode),
            background=str(args.background),
        )
        reference_paths.append(reference_path)

        if args.page_title and page_count == 1:
            page_title = str(args.page_title).strip()
        elif args.page_title:
            page_title = f"{str(args.page_title).strip()} {page_no:02d}"
        else:
            page_title = source_image.stem
        reference_url = f"/runs/{job_id}/01_reference_pages/{reference_path.name}"
        reference_item = {
            "page_no": page_no,
            "title": page_title,
            "prompt": reference_prompt,
            "image": reference_url,
            "generation": {
                "provider": "external_reference_image",
                "source_image": str(source_image),
                "normalized_size": f"{image_width}x{image_height}",
                "resize_mode": str(args.resize_mode),
            },
        }
        reference_items.append(reference_item)
        pages.append(
            build_external_page(
                page_no=page_no,
                page_title=page_title,
                reference_prompt=reference_prompt,
                elements_prompt=elements_prompt,
                reference_url=reference_url,
            )
        )

    if args.content:
        content = str(args.content).strip()
    elif page_count == 1:
        content = f"外部原稿图续跑：{source_images[0].name}"
    else:
        source_parent = source_images[0].parent
        content = f"外部原稿图文件夹续跑：{source_parent.name}（共 {page_count} 张）"
    job_target = JOB_TARGET_REFERENCE_ONLY if bool(args.create_only) else JOB_TARGET_EDITABLE_PPT
    state = build_initial_state(
        job_id=job_id,
        content=content,
        image_preset=image_preset,
        image_quality=image_quality,
        generation_options=generation_options,
        pages=pages,
        reference_items=reference_items,
        job_target=job_target,
        create_only=bool(args.create_only),
    )

    result_payload = runtime.normalize_job_result_payload({})
    if args.create_only:
        result_payload = create_reference_only_delivery(
            job_id=job_id,
            job_dir=job_dir,
            state=state,
            image_width=image_width,
            image_height=image_height,
        )
        state["result"] = result_payload

    request_payload = {
        "content": content,
        "page_count": page_count,
        "image_preset": preset_name,
        "image_quality": image_quality,
        "style_notes": "",
        "job_target": job_target,
        "generation_options": generation_options,
        "include_cover_page": generation_options["include_cover_page"],
        "page_richness_default": generation_options["page_richness_default"],
        "page_richness_map": generation_options["page_richness_map"],
        "reference_style_adherence": generation_options["reference_style_adherence"],
        "style_reference_images": [],
        "external_reference_images": [str(source_image) for source_image in source_images],
        "external_reference_resize_mode": str(args.resize_mode),
    }
    runtime.create_job_record(
        runtime.JOBS_DB_PATH,
        {
            "job_id": job_id,
            "status": state["status"],
            "current_stage": state["current_stage"],
            "title": str(args.title or runtime.build_job_title(content)),
            "content": content,
            "page_count": page_count,
            "image_preset": preset_name,
            "image_quality": image_quality,
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
        "job_id": job_id,
        "job_dir": job_dir,
        "config": config,
        "active_config": active_config,
        "image_preset": image_preset,
        "generation_options": generation_options,
        "content": content,
        "refs_dir": refs_dir,
        "stage1_dir": stage1_dir,
        "stage2_dir": stage2_dir,
        "reference_path": reference_paths[0],
        "reference_paths": reference_paths,
        "page_count": page_count,
        "output_pptx": job_dir / build_editable_ppt_filename(SEPARATE_LAYER_MODE),
    }


def run_job_pipeline_from_created_job(created: dict[str, Any]) -> None:
    runtime.run_job_pipeline(
        str(created["job_id"]),
        Path(created["job_dir"]),
        dict(created["config"]),
        dict(created["active_config"]),
        str(created["content"]),
        int(created.get("page_count") or 1),
        dict(created["image_preset"]),
        "",
        dict(created["generation_options"]),
        Path(created["stage1_dir"]),
        Path(created["stage2_dir"]),
        Path(created["refs_dir"]),
    )


def find_stage(state: dict[str, Any], stage_key: str) -> dict[str, Any]:
    for stage in state.get("stages", []):
        if stage.get("key") == stage_key:
            return stage
    return {}


def ensure_pipeline_succeeded(job_id: str, job_dir: Path) -> None:
    state = runtime.load_job_state(job_id, job_dir) or {}
    status = str(state.get("status", "")).strip()
    if status == "completed":
        return

    error = str(state.get("error", "")).strip()
    current_stage = str(state.get("current_stage", "")).strip() or "unknown"
    if not error:
        stage = find_stage(state, current_stage)
        error = str(stage.get("summary", "")).strip()
    raise RuntimeError(f"任务未完成：job_id={job_id}，stage={current_stage}，status={status}，原因：{error}")


def export_default_editable_ppt(job_id: str, job_dir: Path) -> Path:
    """把可编辑资源包导出成默认拆分页 PPT，并同步写回任务结果。"""
    state, _record = runtime.get_job_state_snapshot(job_id, job_dir)
    if not state:
        raise RuntimeError(f"任务状态不存在：{job_id}")

    job_snapshot = runtime.load_job_snapshot(job_dir)
    job_payload = runtime.build_job_payload_from_state(state, job_snapshot)
    result_payload = runtime.normalize_job_result_payload(job_payload.get("result", {}))
    editable_bundle = runtime.get_editable_delivery_bundle(result_payload)
    bundle_path = Path(str(editable_bundle.get("bundle_path", "")).strip())
    if not bundle_path.exists():
        raise RuntimeError(f"可编辑资源包不存在，无法导出 PPT：{bundle_path}")

    layer_mode = SEPARATE_LAYER_MODE
    output_pptx = job_dir / build_editable_ppt_filename(layer_mode)
    export_payload = runtime.export_editable_delivery(bundle_path, output_pptx, layer_mode=layer_mode)
    editable_delivery = runtime.build_editable_delivery_payload(job_id, job_dir, export_payload)
    result_payload = runtime.set_editable_delivery(result_payload, editable_delivery, layer_mode=layer_mode)

    job_payload["result"] = result_payload
    runtime.write_job_snapshot(job_dir, job_payload)
    runtime.mutate_job_state(job_dir, job_id, lambda current_state: current_state.update({"result": result_payload}))
    return output_pptx


def reset_job_for_resume(job_id: str, job_dir: Path, request_payload: dict[str, Any]) -> None:
    """把已有外部原稿图任务恢复到可继续执行的队列状态。"""
    request_payload["job_target"] = JOB_TARGET_EDITABLE_PPT
    runtime.update_job_record(
        runtime.JOBS_DB_PATH,
        job_id,
        stop_requested=False,
        status="queued",
        request=request_payload,
    )

    def updater(state: dict[str, Any]) -> None:
        state["status"] = "queued"
        state["current_stage"] = "queued"
        state["error"] = ""
        state["stop_requested"] = False
        job_meta = state.setdefault("job_meta", {})
        job_meta["job_target"] = JOB_TARGET_EDITABLE_PPT
        job_meta["job_target_label"] = runtime.TARGET_LABELS[JOB_TARGET_EDITABLE_PPT]
        for stage in state.get("stages", []):
            if stage.get("key") in {"elements_generation", "ppt_export"} and stage.get("status") in {
                "error",
                "interrupted",
                "skipped",
            }:
                stage["status"] = "pending"
                stage["summary"] = "等待继续执行"

    runtime.mutate_job_state(job_dir, job_id, updater)
    runtime.reconcile_resume_state(job_dir, job_id)


def build_resume_payload(job_id: str) -> dict[str, Any]:
    record = runtime.get_job_record(runtime.JOBS_DB_PATH, job_id)
    if not record:
        raise FileNotFoundError(f"任务不存在：{job_id}")
    job_dir = Path(str(record["job_dir"]))
    request_payload = dict(record.get("request", {}))
    config = runtime.read_config()
    image_preset = runtime.resolve_image_preset(
        config,
        str(request_payload.get("image_preset") or record.get("image_preset") or config.get("default_image_preset", "landscape_2k")),
    )
    image_quality = str(request_payload.get("image_quality") or record.get("image_quality") or config.get("image_quality", "medium"))
    active_config = build_active_config(config, image_preset, image_quality)
    generation_options = runtime.resolve_generation_options(
        request_payload.get("generation_options", request_payload),
        config=config,
    )
    reset_job_for_resume(job_id, job_dir, request_payload)
    return {
        "job_id": job_id,
        "job_dir": job_dir,
        "config": config,
        "active_config": active_config,
        "image_preset": image_preset,
        "generation_options": generation_options,
        "content": str(request_payload.get("content", record.get("content", ""))),
        "refs_dir": job_dir / "style_refs",
        "stage1_dir": job_dir / "01_reference_pages",
        "stage2_dir": job_dir / "02_elements_pages",
        "reference_path": job_dir / "01_reference_pages" / "page_01_reference.png",
        "page_count": int(record.get("page_count") or request_payload.get("page_count") or 1),
        "output_pptx": job_dir / build_editable_ppt_filename(SEPARATE_LAYER_MODE),
    }


def main() -> int:
    configure_utf8_console()
    args = parse_args()
    if args.resume_job:
        created = build_resume_payload(str(args.resume_job).strip())
        print(f"继续任务：{created['job_id']}", flush=True)
        print(f"任务目录：{created['job_dir']}", flush=True)
        run_job_pipeline_from_created_job(created)
        ensure_pipeline_succeeded(str(created["job_id"]), Path(created["job_dir"]))
        output_pptx = export_default_editable_ppt(str(created["job_id"]), Path(created["job_dir"]))
        print(f"后续流程执行完成：{created['job_id']}", flush=True)
        print(f"默认可编辑输出：{output_pptx}", flush=True)
        return 0

    created = create_external_reference_job(args)
    print(f"已新建任务：{created['job_id']}", flush=True)
    print(f"任务目录：{created['job_dir']}", flush=True)
    print(f"原稿图数量：{created['page_count']}", flush=True)
    print(f"首张原稿图：{created['reference_path']}", flush=True)
    if args.create_only:
        print("已停在原稿图完成状态，可在界面中继续生成可编辑元素。", flush=True)
        return 0

    print("开始从元素图阶段继续执行后续转换流程...", flush=True)
    run_job_pipeline_from_created_job(created)
    ensure_pipeline_succeeded(str(created["job_id"]), Path(created["job_dir"]))
    output_pptx = export_default_editable_ppt(str(created["job_id"]), Path(created["job_dir"]))
    print(f"后续流程执行完成：{created['job_id']}", flush=True)
    print(f"默认可编辑输出：{output_pptx}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
