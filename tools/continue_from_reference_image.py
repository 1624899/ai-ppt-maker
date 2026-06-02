from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main as runtime  # noqa: E402
from ppt_system.export.delivery_options import (  # noqa: E402
    build_editable_ppt_filename,
)
from ppt_system.export.export_layer_mode import SEPARATE_LAYER_MODE  # noqa: E402
from ppt_system.runtime.console_encoding import configure_utf8_console  # noqa: E402
from ppt_system.web.services.job_submission_runtime import build_active_config  # noqa: E402
from ppt_system.web.services.external_reference_job import (  # noqa: E402
    RESIZE_MODES,
    collect_reference_images,
    create_external_reference_job as create_external_reference_job_service,
)


DEFAULT_REFERENCE_PATH = ROOT / "图片转换"


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


def create_external_reference_job(args: argparse.Namespace) -> dict[str, Any]:
    config = runtime.read_config()
    source_images = collect_reference_images(ROOT, Path(args.reference_path), recursive=bool(args.recursive))
    return create_external_reference_job_service(
        runtime,
        config=config,
        source_images=source_images,
        job_id=str(args.job_id or "").strip(),
        title=str(args.title or "").strip(),
        content=str(args.content or "").strip(),
        page_title=str(args.page_title or "").strip(),
        image_preset_name=str(args.image_preset or "").strip(),
        image_quality=str(args.image_quality or "").strip(),
        resize_mode=str(args.resize_mode),
        background=str(args.background),
        create_only=bool(args.create_only),
    )


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
