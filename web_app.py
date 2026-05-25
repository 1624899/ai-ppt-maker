from __future__ import annotations

import json
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, render_template, request, send_from_directory, stream_with_context

from ppt_system.concurrent_stage import drain_fail_safe_futures
from ppt_system.content_agent import build_content_plan
from ppt_system.export_pipeline import export_web_job_to_pptx
from ppt_system.generation_options import default_generation_options, resolve_generation_options
from ppt_system.generation_prompts import build_elements_prompt
from ppt_system.page_evaluator import evaluate_plan
from ppt_system.job_store import create_job as create_job_record
from ppt_system.job_store import delete_job as delete_job_record
from ppt_system.job_store import get_job as get_job_record
from ppt_system.job_store import init_db as init_job_db
from ppt_system.job_store import list_jobs as list_job_records
from ppt_system.job_store import update_job as update_job_record
from ppt_system.model_config import (
    delete_model_config,
    get_active_model_config,
    list_model_configs,
    read_config as read_json_config,
    set_active_model_config,
    upsert_model_config,
    write_config,
)
from ppt_system.openai_chat_provider import OpenAIChatProvider
from ppt_system.openai_image_provider import OpenAIImageProvider
from ppt_system.stage_resume import has_expected_outputs, reconcile_completed_stages, should_run_stage


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
JOBS_DB_PATH = ROOT / "output" / "jobs.sqlite3"
init_job_db(JOBS_DB_PATH)
JOB_EXECUTOR = ThreadPoolExecutor(max_workers=2)
JOB_STATUS_LOCK = threading.Lock()
JOB_STATUS_CACHE: dict[str, dict[str, Any]] = {}


class JobInterruptedError(RuntimeError):
    pass


def read_config() -> dict[str, Any]:
    return read_json_config(CONFIG_PATH)


def resolve_image_preset(config: dict[str, Any], preset_name: str) -> dict[str, Any]:
    presets = config.get("image_presets", {})
    default_name = str(config.get("default_image_preset", "2k"))
    selected_name = preset_name or default_name
    if selected_name not in presets:
        raise ValueError(f"图像尺寸只能选择：{', '.join(presets.keys())}")

    preset = dict(presets[selected_name])
    preset["name"] = selected_name
    return preset


def build_export_options(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "alpha_threshold": int(config.get("split_alpha_threshold", 8)),
        "min_area": int(config.get("split_min_area", 8)),
        "padding": int(config.get("split_padding", 0)),
        "merge_distance": int(config.get("split_merge_distance", 6)),
        "filter_decorative_fragments": bool(config.get("split_filter_decorative_fragments", True)),
        "skip_enhance": bool(config.get("skip_export_enhance", False)),
        "skip_transparent": bool(config.get("skip_export_transparent", False)),
        "enhance_mode": str(config.get("export_enhance_mode", "builtin")),
        "enhance_command": str(config.get("export_enhance_command", "")),
        "background_mode": str(config.get("export_background_mode", "builtin")),
        "background_command": str(config.get("export_background_command", "")),
        "external_command_timeout_seconds": int(config.get("export_external_command_timeout_seconds", 1800)),
        "script_refine_rounds": int(config.get("text_script_refine_rounds", 1)),
    }


def list_style_reference_images(job_id: str, job_dir: Path) -> list[dict[str, Any]]:
    refs_dir = job_dir / "style_refs"
    if not refs_dir.exists():
        return []
    items: list[dict[str, Any]] = []
    for file in sorted(refs_dir.iterdir(), key=lambda item: item.name.lower()):
        if not file.is_file():
            continue
        items.append(
            {
                "name": file.name,
                "url": f"/runs/{job_id}/style_refs/{file.name}",
                "size": int(file.stat().st_size),
            }
        )
    return items


def copy_style_reference_images(source_job_dir: Path, target_refs_dir: Path) -> list[Path]:
    source_refs_dir = source_job_dir / "style_refs"
    if not source_refs_dir.exists():
        return []
    copied_files: list[Path] = []
    for file in sorted(source_refs_dir.iterdir(), key=lambda item: item.name.lower()):
        if not file.is_file():
            continue
        target = target_refs_dir / file.name
        shutil.copy2(file, target)
        copied_files.append(target)
    return copied_files


def write_error(job_dir: Path, payload: dict[str, Any]) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "error.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_job_state(
    job_id: str,
    content: str,
    page_count: int,
    image_preset: dict[str, Any],
    image_quality: str,
    style_notes: str,
    generation_options: dict[str, Any],
    style_reference_images: list[dict[str, Any]],
) -> dict[str, Any]:
    pages = [
        {
            "page_no": index + 1,
            "title": f"第 {index + 1} 页生成中",
            "status": "pending",
            "reference_image": "",
            "element_image": "",
            "reference_prompt": "",
            "elements_prompt": "",
        }
        for index in range(page_count)
    ]
    return {
        "job_id": job_id,
        "status": "queued",
        "current_stage": "queued",
        "error": "",
        "stop_requested": False,
        "job_meta": {
            "content": content,
            "page_count": page_count,
            "image_preset": image_preset,
            "image_quality": image_quality,
            "style_notes": style_notes,
            "generation_options": generation_options,
            "style_reference_images": style_reference_images,
        },
        "plan": {},
        "pages": pages,
        "reference_pages": [],
        "element_pages": [],
        "stages": [
            {
                "key": "planning",
                "label": "模型规划",
                "status": "pending",
                "summary": "等待对话模型拆解内容结构",
                "logs": [],
                "data": {},
            },
            {
                "key": "reference_generation",
                "label": "参考图生成",
                "status": "pending",
                "summary": "等待生成带文字的 PPT 效果图",
                "logs": [],
                "data": {},
            },
            {
                "key": "elements_generation",
                "label": "元素图生成",
                "status": "pending",
                "summary": "等待生成去文字元素图",
                "logs": [],
                "data": {},
            },
            {
                "key": "ppt_export",
                "label": "PPT 组装",
                "status": "pending",
                "summary": "等待执行图像后处理并导出 PPTX",
                "logs": [],
                "data": {},
            },
        ],
    }


def status_file(job_dir: Path) -> Path:
    return job_dir / "status.json"


def cache_job_state(job_id: str, state: dict[str, Any]) -> None:
    with JOB_STATUS_LOCK:
        JOB_STATUS_CACHE[job_id] = state


def save_job_state(job_dir: Path, state: dict[str, Any]) -> None:
    cache_job_state(state["job_id"], state)
    status_file(job_dir).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    sync_job_record(state["job_id"], state)


def load_job_state(job_id: str, job_dir: Path) -> dict[str, Any] | None:
    with JOB_STATUS_LOCK:
        cached = JOB_STATUS_CACHE.get(job_id)
    if cached:
        return cached
    target = status_file(job_dir)
    if not target.exists():
        return None
    state = json.loads(target.read_text(encoding="utf-8"))
    cache_job_state(job_id, state)
    return state


def mutate_job_state(job_dir: Path, job_id: str, updater) -> dict[str, Any]:
    with JOB_STATUS_LOCK:
        current = JOB_STATUS_CACHE.get(job_id)
        if current is None:
            target = status_file(job_dir)
            if target.exists():
                current = json.loads(target.read_text(encoding="utf-8"))
            else:
                raise RuntimeError(f"找不到任务状态：{job_id}")
        state = json.loads(json.dumps(current, ensure_ascii=False))
        updater(state)
        JOB_STATUS_CACHE[job_id] = state
        status_file(job_dir).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        sync_job_record(job_id, state)
        return state


def append_stage_log(job_dir: Path, job_id: str, stage_key: str, message: str) -> None:
    def updater(state: dict[str, Any]) -> None:
        for stage in state["stages"]:
            if stage["key"] == stage_key:
                stage.setdefault("logs", []).append(message)
                break

    mutate_job_state(job_dir, job_id, updater)


def update_stage(
    job_dir: Path,
    job_id: str,
    stage_key: str,
    *,
    status: str | None = None,
    summary: str | None = None,
    data: dict[str, Any] | None = None,
    current_stage: str | None = None,
    job_status: str | None = None,
) -> None:
    def updater(state: dict[str, Any]) -> None:
        for stage in state["stages"]:
            if stage["key"] == stage_key:
                if status is not None:
                    stage["status"] = status
                if summary is not None:
                    stage["summary"] = summary
                if data is not None:
                    stage["data"] = data
                break
        if current_stage is not None:
            state["current_stage"] = current_stage
        if job_status is not None:
            state["status"] = job_status

    mutate_job_state(job_dir, job_id, updater)


def update_page_state(job_dir: Path, job_id: str, page_no: int, **fields: Any) -> None:
    def updater(state: dict[str, Any]) -> None:
        for page in state["pages"]:
            if int(page["page_no"]) == int(page_no):
                page.update(fields)
                break

    mutate_job_state(job_dir, job_id, updater)


def finalize_job_error(job_dir: Path, job_id: str, stage_key: str, payload: dict[str, Any]) -> None:
    def updater(state: dict[str, Any]) -> None:
        state["status"] = "error"
        state["current_stage"] = stage_key
        state["error"] = payload.get("error", "")
        for stage in state["stages"]:
            if stage["key"] == stage_key:
                stage["status"] = "error"
                stage.setdefault("logs", []).append(payload.get("error", "任务失败"))
                break

    mutate_job_state(job_dir, job_id, updater)
    write_error(job_dir, payload)


def finalize_job_interrupted(job_dir: Path, job_id: str, stage_key: str, message: str) -> None:
    def updater(state: dict[str, Any]) -> None:
        state["status"] = "interrupted"
        state["current_stage"] = stage_key
        state["error"] = ""
        state["stop_requested"] = False
        for stage in state["stages"]:
            if stage["key"] == stage_key and message not in stage.setdefault("logs", []):
                stage["logs"].append(message)
                stage["status"] = "interrupted"
                break

    mutate_job_state(job_dir, job_id, updater)


def mark_job_stopping(job_dir: Path, job_id: str, stage_key: str, message: str) -> None:
    def updater(state: dict[str, Any]) -> None:
        state["status"] = "stopping"
        state["current_stage"] = stage_key
        state["stop_requested"] = True
        for stage in state["stages"]:
            if stage["key"] == stage_key:
                stage["summary"] = message
                stage["status"] = "running"
                logs = stage.setdefault("logs", [])
                if message not in logs:
                    logs.append(message)
                break

    mutate_job_state(job_dir, job_id, updater)


def sync_job_record(job_id: str, state: dict[str, Any]) -> None:
    record = get_job_record(JOBS_DB_PATH, job_id)
    if not record:
        return
    update_job_record(
        JOBS_DB_PATH,
        job_id,
        status=state.get("status", "queued"),
        current_stage=state.get("current_stage", "queued"),
        state=state,
        result=state.get("result", {}),
        stop_requested=state.get("stop_requested", False),
    )


def build_job_title(content: str) -> str:
    text = " ".join(content.split())
    return text[:36] + ("..." if len(text) > 36 else "")


def job_summary(record: dict[str, Any]) -> dict[str, Any]:
    state = record.get("state", {})
    return {
        "job_id": record["job_id"],
        "title": record["title"],
        "status": record["status"],
        "current_stage": record["current_stage"],
        "page_count": record["page_count"],
        "image_preset": record["image_preset"],
        "image_quality": record["image_quality"],
        "style_notes": record["style_notes"],
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "stop_requested": record.get("stop_requested", False),
        "preview_image": _find_preview_image(state),
    }


def enrich_job_state_with_record(state: dict[str, Any], record: dict[str, Any] | None) -> dict[str, Any]:
    merged = json.loads(json.dumps(state, ensure_ascii=False))
    if not record:
        return merged
    job_meta = merged.setdefault("job_meta", {})
    job_meta["content"] = str(job_meta.get("content") or record.get("content") or "")
    job_meta["page_count"] = int(job_meta.get("page_count") or record.get("page_count") or 0)
    job_meta["image_quality"] = str(job_meta.get("image_quality") or record.get("image_quality") or "")
    job_meta["style_notes"] = str(job_meta.get("style_notes") or record.get("style_notes") or "")
    if not isinstance(job_meta.get("generation_options"), dict):
        job_meta["generation_options"] = resolve_generation_options(record.get("request", {}), config=read_config())
    if not job_meta.get("image_preset"):
        config = read_config()
        try:
            job_meta["image_preset"] = resolve_image_preset(config, str(record.get("image_preset") or ""))
        except ValueError:
            job_meta["image_preset"] = {"name": str(record.get("image_preset") or ""), "label": str(record.get("image_preset") or "")}
    if not isinstance(job_meta.get("style_reference_images"), list) or not job_meta.get("style_reference_images"):
        job_meta["style_reference_images"] = list_style_reference_images(str(record["job_id"]), Path(record["job_dir"]))
    return merged


def list_job_summaries(limit: int = 100) -> list[dict[str, Any]]:
    records = list_job_records(JOBS_DB_PATH, limit=limit)
    return [job_summary(record) for record in records]


def _find_preview_image(state: dict[str, Any]) -> str:
    for page in state.get("pages", []):
        if page.get("reference_image"):
            return str(page["reference_image"])
    return ""


def should_stop_job(job_id: str) -> bool:
    record = get_job_record(JOBS_DB_PATH, job_id)
    return bool(record and record.get("stop_requested"))


def remove_job_artifacts(job_dir: Path) -> None:
    if not job_dir.exists():
        return
    try:
        resolved = job_dir.resolve()
    except OSError:
        return
    output_root = (ROOT / "output").resolve()
    if resolved == output_root or output_root not in resolved.parents:
        return
    shutil.rmtree(resolved, ignore_errors=True)


def ensure_job_not_stopped(job_dir: Path, job_id: str, stage_key: str) -> None:
    if should_stop_job(job_id):
        mark_job_stopping(job_dir, job_id, stage_key, "已收到停止请求，等待当前请求完成后暂停")
        raise JobInterruptedError(stage_key)


def _attach_page_evaluations(plan: dict[str, Any], evaluation_result: dict[str, Any]) -> None:
    page_scores = evaluation_result.get("page_scores", [])
    score_map: dict[int, dict[str, Any]] = {}
    for ps in page_scores:
        score_map[int(ps.get("page_no", 0))] = ps
    for page in plan.get("pages", []):
        page_no = int(page.get("page_no", 0))
        if page_no in score_map:
            page["evaluation"] = score_map[page_no]


def extract_pages_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for page in state.get("pages", []):
        pages.append(
            {
                "page_no": int(page["page_no"]),
                "title": page.get("title", f"第 {page['page_no']} 页"),
                "summary": page.get("summary", ""),
                "bullets": page.get("bullets", []),
                "layout_intent": page.get("layout_intent", ""),
                "layout_family": page.get("layout_family", ""),
                "element_plan": page.get("element_plan", []),
                "reference_mode": page.get("reference_mode", "generation"),
                "prompt_profile": page.get("prompt_profile", "compressed"),
                "image_prompt": page.get("reference_prompt", ""),
                "elements_prompt": page.get("elements_prompt", ""),
                "layout_slots": page.get("layout_slots", []),
                "texts": page.get("texts", []),
            }
        )
    return pages


def extract_reference_pages_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    references = list(state.get("reference_pages", []))
    if references:
        return references

    rebuilt: list[dict[str, Any]] = []
    for page in state.get("pages", []):
        reference_image = str(page.get("reference_image", "")).strip()
        if not reference_image:
            continue
        rebuilt.append(
            {
                "page_no": int(page["page_no"]),
                "title": page.get("title", f"第 {page['page_no']} 页"),
                "prompt": page.get("reference_prompt", ""),
                "image": reference_image,
                "generation": {},
            }
        )
    rebuilt.sort(key=lambda item: int(item["page_no"]))
    return rebuilt


def extract_element_pages_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    elements = list(state.get("element_pages", []))
    if elements:
        return elements

    rebuilt: list[dict[str, Any]] = []
    for page in state.get("pages", []):
        element_image = str(page.get("element_image", "")).strip()
        if not element_image:
            continue
        rebuilt.append(
            {
                "page_no": int(page["page_no"]),
                "prompt": page.get("elements_prompt", ""),
                "image": element_image,
                "generation": {},
            }
        )
    rebuilt.sort(key=lambda item: int(item["page_no"]))
    return rebuilt


def reconcile_resume_state(job_dir: Path, job_id: str) -> dict[str, Any]:
    def updater(state: dict[str, Any]) -> None:
        pages = extract_pages_from_state(state)
        references = extract_reference_pages_from_state(state)
        elements = extract_element_pages_from_state(state)
        completion_map = {
            "planning": bool(pages),
            "reference_generation": has_expected_outputs(references, len(pages)),
            "elements_generation": has_expected_outputs(elements, len(references)),
        }
        reconcile_completed_stages(state, completion_map)

    return mutate_job_state(job_dir, job_id, updater)


def submit_reference_task(
    executor: ThreadPoolExecutor,
    job_dir: Path,
    job_id: str,
    page: dict[str, Any],
    stage1_dir: Path,
    image_provider: OpenAIImageProvider,
    style_reference_paths: list[Path],
    reference_mode: str = "generation",
) -> tuple[Any, int, str, Path]:
    page_no = int(page["page_no"])
    prompt = str(page["image_prompt"])
    image_path = stage1_dir / f"page_{page_no:02d}_reference.png"
    prompt_path = stage1_dir / f"page_{page_no:02d}_reference_prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    update_page_state(job_dir, job_id, page_no, status="rendering_reference", reference_prompt=prompt)
    append_stage_log(job_dir, job_id, "reference_generation", f"第 {page_no} 页已进入参考图生成队列")
    future = executor.submit(
        image_provider.generate_reference_page,
        prompt,
        image_path,
        style_reference_paths,
        reference_mode,
    )
    return future, page_no, prompt, image_path


def submit_elements_task(
    executor: ThreadPoolExecutor,
    job_dir: Path,
    job_id: str,
    page_no: int,
    elements_prompt: str,
    stage1_dir: Path,
    stage2_dir: Path,
    image_provider: OpenAIImageProvider,
) -> tuple[Any, int, Path]:
    ref_path = stage1_dir / f"page_{page_no:02d}_reference.png"
    out_path = stage2_dir / f"page_{page_no:02d}_elements.png"
    prompt_path = stage2_dir / f"page_{page_no:02d}_elements_prompt.txt"
    prompt_path.write_text(elements_prompt, encoding="utf-8")
    update_page_state(job_dir, job_id, page_no, status="rendering_elements", elements_prompt=elements_prompt)
    append_stage_log(job_dir, job_id, "elements_generation", f"第 {page_no} 页元素图已进入并发队列")
    future = executor.submit(image_provider.generate_elements_page, elements_prompt, ref_path, out_path)
    return future, page_no, out_path


app = Flask(
    __name__,
    template_folder=str(ROOT / "front" / "templates"),
    static_folder=str(ROOT / "front" / "static"),
)


def static_asset_version() -> str:
    paths = [
        ROOT / "front" / "static" / "app.css",
        ROOT / "front" / "static" / "app.js",
    ]
    latest_mtime = max(int(path.stat().st_mtime) for path in paths if path.exists())
    return str(latest_mtime)


@app.get("/")
def index():
    return render_template("index.html", asset_version=static_asset_version())


@app.after_request
def disable_browser_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.get("/api/config")
def api_config():
    config = read_config()
    return jsonify(
        {
            "max_pages": config["max_pages"],
            "default_pages": config["default_pages"],
            "default_image_preset": config["default_image_preset"],
            "image_presets": config["image_presets"],
            "image_width": config["image_width"],
            "image_height": config["image_height"],
            "generation_mode": config["generation_mode"],
            "api_base_url": config["api_base_url"],
            "image_model": config["image_model"],
            "image_size": config["image_size"],
            "image_resolution": config["image_resolution"],
            "image_quality": config["image_quality"],
            "image_background": config["image_background"],
            "image_output_format": config["image_output_format"],
            "default_include_cover_page": bool(default_generation_options(config)["include_cover_page"]),
            "active_chat_config_id": config.get("active_chat_config_id", ""),
            "active_image_config_id": config.get("active_image_config_id", ""),
        }
    )


@app.get("/api/model-configs")
def api_model_configs():
    config = read_config()
    return jsonify(
        {
            "active_chat_config_id": config.get("active_chat_config_id", ""),
            "active_image_config_id": config.get("active_image_config_id", ""),
            "configs": list_model_configs(config),
        }
    )


@app.post("/api/model-configs/<model_type>")
def api_create_model_config(model_type: str):
    config = read_config()
    try:
        item = upsert_model_config(config, model_type, request.get_json(force=True))
        write_config(CONFIG_PATH, config)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(item)


@app.put("/api/model-configs/<model_type>/<config_id>")
def api_update_model_config(model_type: str, config_id: str):
    config = read_config()
    try:
        item = upsert_model_config(config, model_type, request.get_json(force=True), config_id=config_id)
        write_config(CONFIG_PATH, config)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(item)


@app.delete("/api/model-configs/<model_type>/<config_id>")
def api_delete_model_config(model_type: str, config_id: str):
    config = read_config()
    try:
        delete_model_config(config, model_type, config_id)
        write_config(CONFIG_PATH, config)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True})


@app.post("/api/model-configs/<model_type>/<config_id>/active")
def api_activate_model_config(model_type: str, config_id: str):
    config = read_config()
    try:
        set_active_model_config(config, model_type, config_id)
        write_config(CONFIG_PATH, config)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True})


@app.post("/api/jobs")
def create_job():
    config = read_config()
    content = request.form.get("content", "").strip()
    page_count = int(request.form.get("page_count", config["default_pages"]))
    image_preset_name = request.form.get("image_preset", str(config.get("default_image_preset", "2k")))
    image_quality = request.form.get("image_quality", str(config.get("image_quality", "medium"))).strip().lower()
    style_notes = request.form.get("style_notes", "").strip()
    reuse_style_refs_from_job_id = request.form.get("reuse_style_refs_from_job_id", "").strip()
    generation_options = resolve_generation_options(request.form, config=config)

    if not content:
        return jsonify({"error": "请输入内容。"}), 400
    if page_count < 1 or page_count > int(config["max_pages"]):
        return jsonify({"error": f"页数必须在 1 到 {config['max_pages']} 之间。"}), 400

    try:
        image_preset = resolve_image_preset(config, image_preset_name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    image_width = int(image_preset["width"])
    image_height = int(image_preset["height"])
    if image_quality not in {"low", "medium", "high", "auto"}:
        return jsonify({"error": "图像质量只能选择 low、medium、high 或 auto。"}), 400
    active_config = dict(config)
    active_config["image_width"] = image_width
    active_config["image_height"] = image_height
    active_config["active_image_size"] = str(image_preset["size"])
    active_config["active_image_resolution"] = str(image_preset["resolution"])
    active_config["image_quality"] = image_quality

    job_id = uuid.uuid4().hex[:12]
    job_dir = ROOT / str(config["output_dir"]) / job_id
    refs_dir = job_dir / "style_refs"
    stage1_dir = job_dir / "01_reference_pages"
    stage2_dir = job_dir / "02_elements_pages"
    refs_dir.mkdir(parents=True, exist_ok=True)
    stage1_dir.mkdir(parents=True, exist_ok=True)
    stage2_dir.mkdir(parents=True, exist_ok=True)

    uploaded_style_ref_count = 0
    for file in request.files.getlist("style_images"):
        if file and file.filename:
            target = refs_dir / Path(file.filename).name
            file.save(target)
            uploaded_style_ref_count += 1
    if uploaded_style_ref_count == 0 and reuse_style_refs_from_job_id:
        source_record = get_job_record(JOBS_DB_PATH, reuse_style_refs_from_job_id)
        if source_record:
            copy_style_reference_images(Path(source_record["job_dir"]), refs_dir)
    style_reference_images = list_style_reference_images(job_id, job_dir)
    state = build_job_state(
        job_id,
        content,
        page_count,
        image_preset,
        image_quality,
        style_notes,
        generation_options,
        style_reference_images,
    )
    request_payload = {
        "content": content,
        "page_count": page_count,
        "image_preset": image_preset_name,
        "image_quality": image_quality,
        "style_notes": style_notes,
        "generation_options": generation_options,
        "include_cover_page": generation_options["include_cover_page"],
        "style_reference_images": style_reference_images,
    }
    create_job_record(
        JOBS_DB_PATH,
        {
            "job_id": job_id,
            "status": state["status"],
            "current_stage": state["current_stage"],
            "title": build_job_title(content),
            "content": content,
            "page_count": page_count,
            "image_preset": image_preset_name,
            "image_quality": image_quality,
            "style_notes": style_notes,
            "job_dir": str(job_dir),
            "request": request_payload,
            "state": state,
            "result": {},
            "stop_requested": False,
        },
    )
    save_job_state(job_dir, state)
    JOB_EXECUTOR.submit(
        run_job_pipeline,
        job_id,
        job_dir,
        config,
        active_config,
        content,
        page_count,
        image_preset,
        style_notes,
        generation_options,
        stage1_dir,
        stage2_dir,
        refs_dir,
    )
    return jsonify(state), 202


def run_job_pipeline(
    job_id: str,
    job_dir: Path,
    config: dict[str, Any],
    active_config: dict[str, Any],
    content: str,
    page_count: int,
    image_preset: dict[str, Any],
    style_notes: str,
    generation_options: dict[str, Any],
    stage1_dir: Path,
    stage2_dir: Path,
    refs_dir: Path,
) -> None:
    try:
        state = reconcile_resume_state(job_dir, job_id)
        if not state:
            finalize_job_error(job_dir, job_id, "planning", {"error": "任务状态不存在", "job_id": job_id})
            return
        mutate_job_state(
            job_dir,
            job_id,
            lambda current_state: current_state.update({"status": "running", "error": "", "stop_requested": False}),
        )
        state = load_job_state(job_id, job_dir) or state
        pages = extract_pages_from_state(state)
        references = extract_reference_pages_from_state(state)
        existing_elements = extract_element_pages_from_state(state)

        ensure_job_not_stopped(job_dir, job_id, "planning")
        append_stage_log(job_dir, job_id, "planning", "开始读取启用中的对话模型与生图模型配置")
        chat_profile = get_active_model_config(config, "chat")
        image_profile = get_active_model_config(config, "image")
        chat_provider = OpenAIChatProvider(active_config, chat_profile)
        image_provider = OpenAIImageProvider(active_config, image_profile)
        append_stage_log(job_dir, job_id, "planning", f"对话模型：{chat_provider.model} @ {chat_provider.api_base_url}")
        append_stage_log(job_dir, job_id, "planning", f"生图模型：{image_provider.model} @ {image_provider.api_base_url}")

        style_reference_paths = sorted(
            [
                path
                for path in refs_dir.iterdir()
                if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
            ]
        )
        append_stage_log(job_dir, job_id, "planning", f"参考风格图数量：{len(style_reference_paths)}")

        plan = state.get("plan", {})
        should_execute_planning = should_run_stage(
            state,
            "planning",
            output_ready=bool(pages),
        )
        if should_execute_planning:
            update_stage(
                job_dir,
                job_id,
                "planning",
                status="running",
                summary="正在调用对话模型拆页并生成每页提示词",
                current_stage="planning",
                job_status="running",
            )
            plan = build_content_plan(
                provider=chat_provider,
                content=content,
                page_count=page_count,
                image_width=int(active_config["image_width"]),
                image_height=int(active_config["image_height"]),
                style_notes=style_notes,
                style_image_count=len(style_reference_paths),
                style_reference_paths=style_reference_paths,
                generation_options=generation_options,
            )
            pages = plan["pages"]
            plan["image_preset"] = image_preset
            plan["style_notes"] = style_notes
            plan["generation_options"] = generation_options
            plan["chat_generation"] = {
                "model": chat_provider.model,
                "base_url": chat_provider.api_base_url,
                "profile_id": chat_profile.get("id", ""),
                "profile_name": chat_profile.get("name", ""),
            }

            def planning_done(current_state: dict[str, Any]) -> None:
                current_state["plan"] = plan
                current_state["pages"] = [
                    {
                        "page_no": int(page["page_no"]),
                        "title": page["title"],
                        "summary": page.get("summary", ""),
                        "bullets": page.get("bullets", []),
                        "layout_intent": page.get("layout_intent", ""),
                        "layout_family": page.get("layout_family", ""),
                        "element_plan": page.get("element_plan", {}),
                        "reference_mode": page.get("reference_mode", "generation"),
                        "prompt_profile": page.get("prompt_profile", "compressed"),
                        "evaluation": page.get("evaluation", {}),
                        "status": "planned",
                        "reference_image": "",
                        "element_image": "",
                        "reference_prompt": page.get("image_prompt", ""),
                        "elements_prompt": "",
                        "layout_slots": page.get("layout_slots", []),
                        "texts": page.get("texts", []),
                    }
                    for page in pages
                ]
                style_guide = plan.get("style_guide", {})
                for page_item in current_state["pages"]:
                    page_data = next((p for p in pages if int(p["page_no"]) == int(page_item["page_no"])), {})
                    try:
                        page_item["elements_prompt"] = build_elements_prompt(page_data, style_guide)
                    except TypeError:
                        page_item["elements_prompt"] = build_elements_prompt()

            mutate_job_state(job_dir, job_id, planning_done)

            evaluation_result: dict[str, Any] = {}
            if config.get("enable_page_evaluation", True):
                try:
                    evaluation_result = evaluate_plan(plan, plan.get("style_guide", {}))
                    append_stage_log(
                        job_dir, job_id, "planning",
                        f"评估完成：{evaluation_result.get('summary', '')}",
                    )
                    _attach_page_evaluations(plan, evaluation_result)
                    mutate_job_state(job_dir, job_id, planning_done)

                    retry_limit = int(config.get("page_evaluation_retry_count", 1))
                    for _retry_idx in range(retry_limit):
                        if evaluation_result.get("overall_score", 1.0) >= 0.7:
                            break
                        append_stage_log(job_dir, job_id, "planning", f"评估未通过，自动重试规划（第 {_retry_idx + 1} 次）")
                        plan = build_content_plan(
                            provider=chat_provider,
                            content=content,
                            page_count=page_count,
                            image_width=int(active_config["image_width"]),
                            image_height=int(active_config["image_height"]),
                            style_notes=style_notes,
                            style_image_count=len(style_reference_paths),
                            style_reference_paths=style_reference_paths,
                            generation_options=generation_options,
                        )
                        pages = plan["pages"]
                        plan["image_preset"] = image_preset
                        plan["style_notes"] = style_notes
                        plan["generation_options"] = generation_options
                        plan["chat_generation"] = {
                            "model": chat_provider.model,
                            "base_url": chat_provider.api_base_url,
                            "profile_id": chat_profile.get("id", ""),
                            "profile_name": chat_profile.get("name", ""),
                        }
                        evaluation_result = evaluate_plan(plan, plan.get("style_guide", {}))
                        _attach_page_evaluations(plan, evaluation_result)
                        mutate_job_state(job_dir, job_id, planning_done)
                        append_stage_log(
                            job_dir, job_id, "planning",
                            f"重试后评估：{evaluation_result.get('summary', '')}",
                        )
                except Exception as eval_exc:
                    append_stage_log(job_dir, job_id, "planning", f"评估异常：{eval_exc}")

            update_stage(
                job_dir,
                job_id,
                "planning",
                status="completed",
                summary=f"已完成内容规划，共 {len(pages)} 页",
                data={
                    "style_type": plan.get("style_type", ""),
                    "audience": plan.get("audience", ""),
                    "narrative": plan.get("narrative", ""),
                    "style_guide": plan.get("style_guide", {}),
                    "evaluation": evaluation_result,
                    "pages": [
                        {
                            "page_no": page["page_no"],
                            "title": page["title"],
                            "summary": page.get("summary", ""),
                            "bullets": page.get("bullets", []),
                            "layout_intent": page.get("layout_intent", ""),
                            "layout_family": page.get("layout_family", ""),
                            "element_plan": page.get("element_plan", []),
                            "reference_mode": page.get("reference_mode", "generation"),
                            "prompt_profile": page.get("prompt_profile", "compressed"),
                            "evaluation": page.get("evaluation", {}),
                            "image_prompt": page.get("image_prompt", ""),
                        }
                        for page in pages
                    ],
                },
            )
            append_stage_log(job_dir, job_id, "planning", f"规划完成，识别风格：{plan.get('style_type', '')}")
            if plan.get("style_guide", {}).get("style_name"):
                append_stage_log(
                    job_dir,
                    job_id,
                    "planning",
                    f"参考图风格锚点：{plan['style_guide'].get('style_name', '')}（来源：{plan['style_guide'].get('source', 'unknown')}）",
                )
        else:
            append_stage_log(job_dir, job_id, "planning", "检测到已有规划结果，继续从已保存进度执行")

        stage1_concurrency = max(1, int(config.get("stage1_concurrency", 1)))
        stage1_stop_requested = False
        pending_reference_pages = []
        for page in pages:
            page_no = int(page["page_no"])
            prompt = str(page["image_prompt"])
            existing_reference = next((item for item in references if int(item["page_no"]) == page_no), None)
            if existing_reference:
                update_page_state(
                    job_dir,
                    job_id,
                    page_no,
                    status="reference_done",
                    reference_image=existing_reference["image"],
                    reference_prompt=prompt,
                )
                continue
            pending_reference_pages.append(page)

        should_execute_reference_generation = should_run_stage(
            state,
            "reference_generation",
            output_ready=has_expected_outputs(references, len(pages)),
        )
        if should_execute_reference_generation:
            update_stage(
                job_dir,
                job_id,
                "reference_generation",
                status="running",
                summary="正在逐页生成带文字参考图",
                current_stage="reference_generation",
            )
        else:
            append_stage_log(job_dir, job_id, "reference_generation", "检测到已有参考图结果，继续从已保存进度执行")
        append_stage_log(job_dir, job_id, "reference_generation", f"第一阶段并发数：{stage1_concurrency}")

        style_inputs = style_reference_paths if bool(config.get("use_style_refs_for_first_stage", True)) else []
        with ThreadPoolExecutor(max_workers=stage1_concurrency) as executor:
            futures: dict[Any, tuple[dict[str, Any], int, str, Path]] = {}
            pending_index = 0
            def refill_reference_tasks() -> None:
                nonlocal pending_index, stage1_stop_requested
                if should_stop_job(job_id):
                    stage1_stop_requested = True
                    mark_job_stopping(
                        job_dir,
                        job_id,
                        "reference_generation",
                        "已收到停止请求，等待当前已发出的参考图完成后暂停",
                    )
                    return

                while (not stage1_stop_requested) and pending_index < len(pending_reference_pages) and len(futures) < stage1_concurrency:
                    page = pending_reference_pages[pending_index]
                    reference_mode = str(page.get("reference_mode", "generation"))
                    future, page_no, prompt, image_path = submit_reference_task(
                        executor,
                        job_dir,
                        job_id,
                        page,
                        stage1_dir,
                        image_provider,
                        style_inputs if reference_mode == "edit_with_refs" else [],
                        reference_mode=reference_mode,
                    )
                    futures[future] = (page, page_no, prompt, image_path)
                    pending_index += 1

            def on_reference_success(task: tuple[dict[str, Any], int, str, Path], generation_meta: dict[str, Any]) -> None:
                page, page_no, prompt, image_path = task
                reference_item = {
                    "page_no": page_no,
                    "title": page["title"],
                    "prompt": prompt,
                    "image": f"/runs/{job_id}/01_reference_pages/{image_path.name}",
                    "generation": generation_meta,
                }
                references.append(reference_item)
                update_page_state(
                    job_dir,
                    job_id,
                    page_no,
                    status="reference_done",
                    reference_image=reference_item["image"],
                )
                mutate_job_state(
                    job_dir,
                    job_id,
                    lambda current_state, item=reference_item: current_state.setdefault("reference_pages", []).append(item),
                )
                append_stage_log(job_dir, job_id, "reference_generation", f"第 {page_no} 页参考图已完成")

            def on_reference_error(task: tuple[dict[str, Any], int, str, Path], exc: BaseException) -> None:
                _, page_no, _, _ = task
                update_page_state(job_dir, job_id, page_no, status="planned")
                append_stage_log(job_dir, job_id, "reference_generation", f"第 {page_no} 页参考图生成失败：{exc}")

            refill_reference_tasks()
            stage1_error = drain_fail_safe_futures(
                futures,
                refill=refill_reference_tasks,
                on_success=on_reference_success,
                on_error=on_reference_error,
            )

        if stage1_stop_requested:
            raise JobInterruptedError("reference_generation")
        if stage1_error is not None:
            raise stage1_error

        references.sort(key=lambda item: int(item["page_no"]))

        def save_references(current_state: dict[str, Any]) -> None:
            current_state["reference_pages"] = references

        mutate_job_state(job_dir, job_id, save_references)
        update_stage(
            job_dir,
            job_id,
            "reference_generation",
            status="completed",
            summary=f"已完成 {len(references)} 张带文字参考图",
            data={"pages": references},
        )

        state = load_job_state(job_id, job_dir) or state
        page_prompt_map: dict[int, str] = {}
        for sp in state.get("pages", []):
            page_prompt_map[int(sp["page_no"])] = str(sp.get("elements_prompt", ""))
        fallback_elements_prompt = build_elements_prompt()

        element_results: list[dict[str, Any]] = list(existing_elements)
        stage2_concurrency = max(1, int(config["stage2_concurrency"]))
        stage2_stop_requested = False
        pending_element_pages: list[int] = []
        for ref in references:
            page_no = int(ref["page_no"])
            existing_element = next((item for item in element_results if int(item["page_no"]) == page_no), None)
            if existing_element:
                update_page_state(
                    job_dir,
                    job_id,
                    page_no,
                    status="completed",
                    element_image=existing_element["image"],
                )
                continue
            pending_element_pages.append(page_no)

        should_execute_elements_generation = should_run_stage(
            state,
            "elements_generation",
            output_ready=has_expected_outputs(element_results, len(references)),
        )
        if should_execute_elements_generation:
            update_stage(
                job_dir,
                job_id,
                "elements_generation",
                status="running",
                summary="正在并发生成去文字元素图",
                current_stage="elements_generation",
            )
        else:
            append_stage_log(job_dir, job_id, "elements_generation", "检测到已有元素图结果，继续从已保存进度执行")
        append_stage_log(job_dir, job_id, "elements_generation", "按页动态 Prompt 生成元素图")

        with ThreadPoolExecutor(max_workers=stage2_concurrency) as executor:
            futures: dict[Any, tuple[int, Path]] = {}
            pending_index = 0
            def refill_elements_tasks() -> None:
                nonlocal pending_index, stage2_stop_requested
                if should_stop_job(job_id):
                    stage2_stop_requested = True
                    mark_job_stopping(
                        job_dir,
                        job_id,
                        "elements_generation",
                        "已收到停止请求，等待当前已发出的元素图完成后暂停",
                    )
                    return

                while (not stage2_stop_requested) and pending_index < len(pending_element_pages) and len(futures) < stage2_concurrency:
                    page_no = pending_element_pages[pending_index]
                    per_page_prompt = str(page_prompt_map.get(page_no, "")) or fallback_elements_prompt
                    future, task_page_no, out_path = submit_elements_task(
                        executor,
                        job_dir,
                        job_id,
                        page_no,
                        per_page_prompt,
                        stage1_dir,
                        stage2_dir,
                        image_provider,
                    )
                    futures[future] = (task_page_no, out_path)
                    pending_index += 1

            def on_elements_success(task: tuple[int, Path], generation_meta: dict[str, Any]) -> None:
                page_no, out_path = task
                used_prompt = str(page_prompt_map.get(page_no, "")) or fallback_elements_prompt
                element_item = {
                    "page_no": page_no,
                    "prompt": used_prompt,
                    "image": f"/runs/{job_id}/02_elements_pages/{out_path.name}",
                    "generation": generation_meta,
                }
                element_results.append(element_item)
                update_page_state(
                    job_dir,
                    job_id,
                    page_no,
                    status="completed",
                    element_image=element_item["image"],
                )
                mutate_job_state(
                    job_dir,
                    job_id,
                    lambda current_state, item=element_item: current_state.setdefault("element_pages", []).append(item),
                )
                append_stage_log(job_dir, job_id, "elements_generation", f"第 {page_no} 页元素图生成完成")

            def on_elements_error(task: tuple[int, Path], exc: BaseException) -> None:
                page_no, _ = task
                update_page_state(job_dir, job_id, page_no, status="reference_done")
                append_stage_log(job_dir, job_id, "elements_generation", f"第 {page_no} 页元素图生成失败：{exc}")

            refill_elements_tasks()
            stage2_error = drain_fail_safe_futures(
                futures,
                refill=refill_elements_tasks,
                on_success=on_elements_success,
                on_error=on_elements_error,
            )

        if stage2_stop_requested:
            raise JobInterruptedError("elements_generation")
        if stage2_error is not None:
            raise stage2_error

        element_results.sort(key=lambda item: item["page_no"])
        job = {
            "job_id": job_id,
            "mode": config["generation_mode"],
            "content": content,
            "plan": plan,
            "pages": pages,
            "model_profiles": {
                "chat": {
                    "id": chat_profile.get("id", ""),
                    "name": chat_profile.get("name", ""),
                    "model": chat_provider.model,
                    "base_url": chat_provider.api_base_url,
                },
                "image": {
                    "id": image_profile.get("id", ""),
                    "name": image_profile.get("name", ""),
                    "model": image_provider.model,
                    "base_url": image_provider.api_base_url,
                },
            },
            "reference_pages": references,
            "element_pages": element_results,
            "export": {},
        }
        (job_dir / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        (job_dir / "config.snapshot.json").write_text(
            json.dumps(active_config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        def save_generated_job(current_state: dict[str, Any]) -> None:
            current_state["element_pages"] = element_results
            current_state["reference_pages"] = references
            current_state["result"] = job
            current_state["stop_requested"] = False

        mutate_job_state(job_dir, job_id, save_generated_job)
        update_stage(
            job_dir,
            job_id,
            "elements_generation",
            status="completed",
            summary=f"已完成 {len(element_results)} 张去文字元素图",
            data={"pages": element_results},
        )

        ensure_job_not_stopped(job_dir, job_id, "ppt_export")
        update_stage(
            job_dir,
            job_id,
            "ppt_export",
            status="running",
            summary="正在执行图像后处理并导出 PPTX",
            current_stage="ppt_export",
        )

        export_work_dir = job_dir / "03_ppt_build"
        export_project_path = job_dir / "project.generated.json"
        export_pptx_path = job_dir / "result.pptx"
        export_options = build_export_options(active_config)

        def export_stage_logger(message: str) -> None:
            append_stage_log(job_dir, job_id, "ppt_export", message)

        def export_page_logger(page_no: int, message: str) -> None:
            append_stage_log(job_dir, job_id, "ppt_export", f"第 {page_no} 页：{message}")

        def export_stop_checker() -> bool:
            if should_stop_job(job_id):
                mark_job_stopping(
                    job_dir,
                    job_id,
                    "ppt_export",
                    "已收到停止请求，等待当前页后处理完成后暂停",
                )
                return True
            return False

        try:
            export_result = export_web_job_to_pptx(
                job,
                job_dir,
                title=build_job_title(content),
                image_width=int(active_config["image_width"]),
                image_height=int(active_config["image_height"]),
                work_dir=export_work_dir,
                output_pptx=export_pptx_path,
                project_path=export_project_path,
                chat_provider=chat_provider,
                stage_logger=export_stage_logger,
                page_logger=export_page_logger,
                stop_checker=export_stop_checker,
                **export_options,
            )
        except InterruptedError as exc:
            raise JobInterruptedError("ppt_export") from exc

        job["export"] = export_result
        (job_dir / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")

        def complete_job(current_state: dict[str, Any]) -> None:
            current_state["status"] = "completed"
            current_state["current_stage"] = "completed"
            current_state["element_pages"] = element_results
            current_state["reference_pages"] = references
            current_state["result"] = job
            current_state["stop_requested"] = False

        mutate_job_state(job_dir, job_id, complete_job)
        update_stage(
            job_dir,
            job_id,
            "ppt_export",
            status="completed",
            summary=f"已导出 PPTX，共 {int(export_result.get('page_count', 0))} 页",
            data=export_result,
            current_stage="completed",
            job_status="completed",
        )
        update_job_record(JOBS_DB_PATH, job_id, stop_requested=False)
    except JobInterruptedError as exc:
        finalize_job_interrupted(job_dir, job_id, str(exc), "任务已暂停，可稍后继续")
        update_job_record(JOBS_DB_PATH, job_id, status="interrupted", current_stage=str(exc), stop_requested=False)
    except Exception as exc:
        stage_key = "reference_generation"
        current_state = load_job_state(job_id, job_dir) or {}
        if current_state.get("current_stage") == "ppt_export":
            stage_key = "ppt_export"
        elif current_state.get("current_stage") == "elements_generation":
            stage_key = "elements_generation"
        elif current_state.get("current_stage") == "planning":
            stage_key = "planning"
        finalize_job_error(job_dir, job_id, stage_key, {"error": str(exc), "job_id": job_id, "stage": stage_key})


@app.get("/api/jobs/<job_id>")
def api_job_status(job_id: str):
    config = read_config()
    job_dir = ROOT / str(config["output_dir"]) / job_id
    state = load_job_state(job_id, job_dir)
    if not state:
        return jsonify({"error": "任务不存在"}), 404
    record = get_job_record(JOBS_DB_PATH, job_id)
    return jsonify(enrich_job_state_with_record(state, record))


@app.get("/api/jobs/<job_id>/stream")
def api_job_stream(job_id: str):
    config = read_config()
    job_dir = ROOT / str(config["output_dir"]) / job_id
    initial_state = load_job_state(job_id, job_dir)
    if not initial_state:
        return jsonify({"error": "任务不存在"}), 404

    @stream_with_context
    def event_stream():
        last_payload = ""
        heartbeat_at = time.monotonic()
        yield "retry: 1500\n\n"
        while True:
            state = load_job_state(job_id, job_dir)
            if not state:
                yield 'event: error\ndata: {"error":"任务不存在"}\n\n'
                break

            record = get_job_record(JOBS_DB_PATH, job_id)
            payload = json.dumps(enrich_job_state_with_record(state, record), ensure_ascii=False)
            if payload != last_payload:
                last_payload = payload
                yield f"event: job\ndata: {payload}\n\n"
                heartbeat_at = time.monotonic()

            if state.get("status") in {"completed", "error", "interrupted"}:
                break

            now = time.monotonic()
            if now - heartbeat_at >= 15:
                yield ": keep-alive\n\n"
                heartbeat_at = now
            time.sleep(0.8)

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/jobs")
def api_job_history():
    return jsonify({"items": list_job_summaries(limit=100)})


@app.delete("/api/jobs/<job_id>")
def api_delete_job(job_id: str):
    record = get_job_record(JOBS_DB_PATH, job_id)
    if not record:
        return jsonify({"error": "任务不存在"}), 404
    if record["status"] in {"queued", "running", "stopping"}:
        return jsonify({"error": "运行中任务不能删除，请先停止并等待暂停后再删除。"}), 400
    remove_job_artifacts(Path(record["job_dir"]))
    delete_job_record(JOBS_DB_PATH, job_id)
    with JOB_STATUS_LOCK:
        JOB_STATUS_CACHE.pop(job_id, None)
    return jsonify({"ok": True})


@app.get("/api/jobs/stream")
def api_job_history_stream():
    @stream_with_context
    def event_stream():
        last_payload = ""
        heartbeat_at = time.monotonic()
        yield "retry: 2000\n\n"
        while True:
            payload = json.dumps({"items": list_job_summaries(limit=100)}, ensure_ascii=False)
            if payload != last_payload:
                last_payload = payload
                yield f"event: history\ndata: {payload}\n\n"
                heartbeat_at = time.monotonic()
            now = time.monotonic()
            if now - heartbeat_at >= 15:
                yield ": keep-alive\n\n"
                heartbeat_at = now
            time.sleep(1.2)

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/api/jobs/<job_id>/interrupt")
def api_interrupt_job(job_id: str):
    record = get_job_record(JOBS_DB_PATH, job_id)
    if not record:
        return jsonify({"error": "任务不存在"}), 404
    if record["status"] not in {"queued", "running"}:
        return jsonify({"error": "只有运行中任务可以中断。"}), 400
    update_job_record(JOBS_DB_PATH, job_id, stop_requested=True, status="stopping")
    job_dir = Path(record["job_dir"])

    def updater(state: dict[str, Any]) -> None:
        state["stop_requested"] = True
        state["status"] = "stopping"

    mutate_job_state(job_dir, job_id, updater)
    return jsonify({"ok": True})


@app.post("/api/jobs/<job_id>/resume")
def api_resume_job(job_id: str):
    record = get_job_record(JOBS_DB_PATH, job_id)
    if not record:
        return jsonify({"error": "任务不存在"}), 404
    if record["status"] not in {"interrupted", "error"}:
        return jsonify({"error": "当前任务状态不支持继续。"}), 400
    request_payload = record.get("request", {})
    config = read_config()
    generation_options = resolve_generation_options(request_payload.get("generation_options", request_payload), config=config)
    try:
        image_preset = resolve_image_preset(config, str(request_payload.get("image_preset", config["default_image_preset"])))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    active_config = dict(config)
    active_config["image_width"] = int(image_preset["width"])
    active_config["image_height"] = int(image_preset["height"])
    active_config["active_image_size"] = str(image_preset["size"])
    active_config["active_image_resolution"] = str(image_preset["resolution"])
    active_config["image_quality"] = str(request_payload.get("image_quality", config.get("image_quality", "medium")))
    job_dir = Path(record["job_dir"])
    refs_dir = job_dir / "style_refs"
    stage1_dir = job_dir / "01_reference_pages"
    stage2_dir = job_dir / "02_elements_pages"
    update_job_record(JOBS_DB_PATH, job_id, stop_requested=False, status="queued")

    def updater(state: dict[str, Any]) -> None:
        state["stop_requested"] = False
        state["status"] = "queued"
        state["error"] = ""

    mutate_job_state(job_dir, job_id, updater)
    reconcile_resume_state(job_dir, job_id)
    JOB_EXECUTOR.submit(
        run_job_pipeline,
        job_id,
        job_dir,
        config,
        active_config,
        str(request_payload.get("content", record["content"])),
        int(request_payload.get("page_count", record["page_count"])),
        image_preset,
        str(request_payload.get("style_notes", record["style_notes"])),
        generation_options,
        stage1_dir,
        stage2_dir,
        refs_dir,
    )
    state = load_job_state(job_id, job_dir)
    return jsonify(state or {"ok": True})


@app.get("/runs/<job_id>/<path:filename>")
def serve_run_file(job_id: str, filename: str):
    config = read_config()
    directory = ROOT / str(config["output_dir"]) / job_id
    return send_from_directory(directory, filename)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=7860, debug=False)
