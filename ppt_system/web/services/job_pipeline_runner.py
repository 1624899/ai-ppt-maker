from __future__ import annotations

import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ppt_system.export.delivery_options import build_editable_ppt_filename
from ppt_system.export.export_layer_mode import SEPARATE_LAYER_MODE
from ppt_system.export.export_pipeline import export_web_job_to_pptx
from ppt_system.export.reference_preview_export import export_reference_images_to_pptx
from ppt_system.export.stage_resume import has_expected_outputs, should_run_stage
from ppt_system.generation.content_agent import build_content_plan
from ppt_system.generation.generation_prompts import build_elements_prompt
from ppt_system.generation.page_evaluator import evaluate_plan
from ppt_system.generation.page_image_pipeline import run_page_image_pipeline
from ppt_system.generation.planning_state import has_complete_planning_state
from ppt_system.integrations.model_config import get_active_model_config
from ppt_system.integrations.openai_chat_provider import OpenAIChatProvider
from ppt_system.integrations.openai_image_provider import OpenAIImageProvider
from ppt_system.jobs.job_delivery_state import (
    build_reference_delivery_payload,
    normalize_job_result_payload,
    set_editable_delivery_bundle,
    set_reference_delivery,
)
from ppt_system.jobs.job_errors import JobInterruptedError
from ppt_system.jobs.job_interrupt_signal import clear_job_stop_request
from ppt_system.jobs.job_status_messages import INTERRUPTED_MESSAGE, STOPPING_MESSAGE
from ppt_system.jobs.job_store import update_job as update_job_record
from ppt_system.jobs.job_targets import get_terminal_stage, should_continue_after_stage
from ppt_system.web.runtime import get_runtime_module
from ppt_system.web.services.app_config_runtime import build_export_options
from ppt_system.web.services.job_image_tasks import submit_elements_task, submit_reference_task
from ppt_system.web.services.job_snapshot_runtime import build_job_payload, write_job_snapshot
from ppt_system.web.services.job_state_runtime import (
    _attach_page_evaluations,
    append_stage_log,
    build_job_title,
    ensure_job_not_stopped,
    extract_element_pages_from_state,
    extract_pages_from_state,
    extract_reference_pages_from_state,
    finalize_job_completed,
    finalize_job_error,
    finalize_job_interrupted,
    get_job_target_from_state,
    load_job_state,
    mark_job_stopping,
    mutate_job_state,
    reconcile_resume_state,
    should_stop_job,
    update_page_state,
    update_stage,
)
from ppt_system.web.services.plan_version_store import get_active_plan_version, save_plan_version
from ppt_system.web.services.workflow_policy import (
    AWAITING_PLAN_CONFIRMATION_STATUS,
    mark_awaiting_plan_confirmation,
    should_pause_after_planning,
)


def _jobs_db_path() -> Path:
    return get_runtime_module().JOBS_DB_PATH


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
        job_target = get_job_target_from_state(state)
        terminal_stage = get_terminal_stage(job_target)
        ensure_job_not_stopped(job_dir, job_id, "queued")
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
            output_ready=has_complete_planning_state(state),
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
                        "page_richness": page.get("page_richness", ""),
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
                            "page_richness": page.get("page_richness", ""),
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
                    f"原稿图风格锚点：{plan['style_guide'].get('style_name', '')}（来源：{plan['style_guide'].get('source', 'unknown')}）",
                )
        else:
            append_stage_log(job_dir, job_id, "planning", "检测到已有规划结果，继续从已保存进度执行")

        state = load_job_state(job_id, job_dir) or state
        if should_execute_planning or not get_active_plan_version(state):
            mutate_job_state(
                job_dir,
                job_id,
                lambda current_state: save_plan_version(
                    current_state,
                    source="model",
                    summary="模型初始规划",
                ),
            )
            state = load_job_state(job_id, job_dir) or state

        if should_pause_after_planning(state):
            append_stage_log(job_dir, job_id, "planning", "分步规划模式已暂停，等待用户确认规划")

            def pause_after_planning(current_state):
                mark_awaiting_plan_confirmation(current_state)
                for stage in current_state.get("stages", []):
                    if isinstance(stage, dict) and stage.get("key") == "planning":
                        stage["status"] = "completed"
                        stage["summary"] = "规划已生成，等待确认后继续生成"
                        break

            mutate_job_state(job_dir, job_id, pause_after_planning)
            update_job_record(
                _jobs_db_path(),
                job_id,
                status=AWAITING_PLAN_CONFIRMATION_STATUS,
                current_stage="planning",
                stop_requested=False,
            )
            return

        stage1_concurrency = max(1, int(config.get("stage1_concurrency", 1)))
        stage2_concurrency = max(1, int(config["stage2_concurrency"]))
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

        state = load_job_state(job_id, job_dir) or state
        page_prompt_map: dict[int, str] = {}
        for sp in state.get("pages", []):
            page_prompt_map[int(sp["page_no"])] = str(sp.get("elements_prompt", ""))
        fallback_elements_prompt = build_elements_prompt()
        element_results: list[dict[str, Any]] = list(existing_elements)
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
                summary="正在逐页生成带文字原稿图",
                current_stage="reference_generation",
            )
        else:
            append_stage_log(job_dir, job_id, "reference_generation", "检测到已有原稿图结果，继续从已保存进度执行")
        append_stage_log(job_dir, job_id, "reference_generation", f"第一阶段并发数：{stage1_concurrency}")

        should_execute_elements_generation = should_run_stage(
            state,
            "elements_generation",
            output_ready=has_expected_outputs(element_results, len(pages)),
        )
        should_generate_elements = should_continue_after_stage(job_target, "reference_generation")
        if should_generate_elements:
            if should_execute_elements_generation:
                update_stage(
                    job_dir,
                    job_id,
                    "elements_generation",
                    status="running",
                    summary="正在按页流水线生成去文字元素图",
                    current_stage="elements_generation",
                )
            else:
                append_stage_log(job_dir, job_id, "elements_generation", "检测到已有元素图结果，继续从已保存进度执行")
            append_stage_log(job_dir, job_id, "elements_generation", f"第二阶段并发数：{stage2_concurrency}")
            append_stage_log(job_dir, job_id, "elements_generation", "按页动态 Prompt 生成元素图")
            append_stage_log(job_dir, job_id, "elements_generation", "原稿图单页完成后将立即触发对应元素图生成")

        style_inputs = style_reference_paths if bool(config.get("use_style_refs_for_first_stage", True)) else []

        def submit_reference(executor: ThreadPoolExecutor, page: dict[str, Any]) -> tuple[Any, tuple[dict[str, Any], int, str, Path]]:
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
            return future, (page, page_no, prompt, image_path)

        def submit_elements(executor: ThreadPoolExecutor, page_no: int) -> tuple[Any, tuple[int, Path]]:
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
            return future, (task_page_no, out_path)

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
            append_stage_log(job_dir, job_id, "reference_generation", f"第 {page_no} 页原稿图已完成")

        def on_reference_error(task: tuple[dict[str, Any], int, str, Path], exc: BaseException) -> None:
            _, page_no, _, _ = task
            update_page_state(job_dir, job_id, page_no, status="planned")
            append_stage_log(job_dir, job_id, "reference_generation", f"第 {page_no} 页原稿图生成失败：{exc}")

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

        def on_pipeline_stop(stage_key: str) -> None:
            message = STOPPING_MESSAGE
            mark_job_stopping(job_dir, job_id, stage_key, message)

        pipeline_result = run_page_image_pipeline(
            pending_reference_pages=pending_reference_pages if should_execute_reference_generation else [],
            pending_element_page_numbers=pending_element_pages,
            reference_concurrency=stage1_concurrency,
            element_concurrency=stage2_concurrency,
            enable_elements=should_generate_elements,
            get_page_no=lambda page: int(page["page_no"]),
            submit_reference=submit_reference,
            submit_elements=submit_elements,
            on_reference_success=on_reference_success,
            on_reference_error=on_reference_error,
            on_elements_success=on_elements_success,
            on_elements_error=on_elements_error,
            should_stop=lambda: should_stop_job(job_id),
            on_stop=on_pipeline_stop,
        )

        if pipeline_result.stopped_stage:
            raise JobInterruptedError(pipeline_result.stopped_stage)
        if pipeline_result.first_error is not None:
            raise pipeline_result.first_error

        references.sort(key=lambda item: int(item["page_no"]))

        def save_references(current_state: dict[str, Any]) -> None:
            current_state["reference_pages"] = references

        mutate_job_state(job_dir, job_id, save_references)
        update_stage(
            job_dir,
            job_id,
            "reference_generation",
            status="completed",
            summary=f"已完成 {len(references)} 张带文字原稿图",
            data={"pages": references},
        )

        if not should_continue_after_stage(job_target, "reference_generation"):
            job_result: dict[str, Any] = normalize_job_result_payload({})
            preview_pptx_path = job_dir / "result.reference_only.pptx"
            preview_export = export_reference_images_to_pptx(
                references,
                job_dir,
                preview_pptx_path,
                image_width=int(active_config["image_width"]),
                image_height=int(active_config["image_height"]),
            )
            reference_delivery = build_reference_delivery_payload(
                job_id,
                job_dir,
                preview_pptx_path,
                page_count=int(preview_export["page_count"]),
                logical_page_count=len(references),
            )
            job_result = set_reference_delivery(job_result, reference_delivery)
            job = build_job_payload(
                job_id=job_id,
                config=config,
                content=content,
                plan=plan,
                pages=pages,
                references=references,
                element_pages=[],
                chat_provider=chat_provider,
                chat_profile=chat_profile,
                image_provider=image_provider,
                image_profile=image_profile,
                result_payload=job_result,
            )
            write_job_snapshot(job_dir, job)
            finalize_job_completed(
                job_dir,
                job_id,
                load_job_state(job_id, job_dir) or state,
                job_result,
                terminal_stage=terminal_stage,
                summary=f"已完成 {len(references)} 张原稿图，可生成图片PPT",
            )
            return

        element_results.sort(key=lambda item: item["page_no"])
        job_result = normalize_job_result_payload({})
        job = build_job_payload(
            job_id=job_id,
            config=config,
            content=content,
            plan=plan,
            pages=pages,
            references=references,
            element_pages=element_results,
            chat_provider=chat_provider,
            chat_profile=chat_profile,
            image_provider=image_provider,
            image_profile=image_profile,
            result_payload=job_result,
        )
        write_job_snapshot(job_dir, job)
        (job_dir / "config.snapshot.json").write_text(
            json.dumps(active_config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        def save_generated_job(current_state: dict[str, Any]) -> None:
            current_state["element_pages"] = element_results
            current_state["reference_pages"] = references
            current_state["result"] = job_result
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
            summary="正在生成可编辑元素资源与文字脚本",
            current_stage="ppt_export",
        )

        export_work_dir = job_dir / "03_ppt_build"
        export_project_path = job_dir / "project.generated.json"
        export_bundle_path = export_work_dir / "editable_delivery.bundle.json"
        export_pptx_path = job_dir / build_editable_ppt_filename(SEPARATE_LAYER_MODE)
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
                    STOPPING_MESSAGE,
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
                bundle_path=export_bundle_path,
                chat_provider=chat_provider,
                stage_logger=export_stage_logger,
                page_logger=export_page_logger,
                stop_checker=export_stop_checker,
                **export_options,
            )
        except InterruptedError as exc:
            raise JobInterruptedError("ppt_export") from exc

        job_result = set_editable_delivery_bundle(
            job_result,
            {
                "bundle_path": str(export_result.get("bundle_path", "")),
                "bundle_url": str(export_result.get("bundle_url", "")),
                "project_path": str(export_result.get("project_path", "")),
                "project_url": str(export_result.get("project_url", "")),
                "default_pptx_path": str(export_result.get("default_pptx_path", "")),
                "default_pptx_url": str(export_result.get("default_pptx_url", "")),
                "logical_page_count": int(export_result.get("logical_page_count", len(pages))),
                "page_count": int(export_result.get("page_count", 0)),
                "text_script_path": str(export_result.get("text_script_path", "")),
                "assets": export_result.get("assets", {}),
                "page_results": export_result.get("page_results", []),
                "layer_mode": str(export_result.get("layer_mode", SEPARATE_LAYER_MODE)),
                "delivery_mode": str(export_result.get("delivery_mode", "")),
            },
        )
        job = build_job_payload(
            job_id=job_id,
            config=config,
            content=content,
            plan=plan,
            pages=pages,
            references=references,
            element_pages=element_results,
            chat_provider=chat_provider,
            chat_profile=chat_profile,
            image_provider=image_provider,
            image_profile=image_profile,
            result_payload=job_result,
        )
        write_job_snapshot(job_dir, job)

        def complete_job(current_state: dict[str, Any]) -> None:
            current_state["status"] = "completed"
            current_state["current_stage"] = "ppt_export"
            current_state["element_pages"] = element_results
            current_state["reference_pages"] = references
            current_state["result"] = job_result
            current_state["stop_requested"] = False

        mutate_job_state(job_dir, job_id, complete_job)
        finalize_job_completed(
            job_dir,
            job_id,
            load_job_state(job_id, job_dir) or state,
            job_result,
            terminal_stage=terminal_stage,
            summary=f"已完成可编辑元素生成，共 {len(element_results)} 页，可继续导出可编辑PPT",
        )
    except JobInterruptedError as exc:
        finalize_job_interrupted(job_dir, job_id, str(exc), INTERRUPTED_MESSAGE)
        update_job_record(_jobs_db_path(), job_id, status="interrupted", current_stage=str(exc), stop_requested=False)
        clear_job_stop_request(job_dir, job_id)
    except Exception as exc:
        stage_key = "reference_generation"
        current_state = load_job_state(job_id, job_dir) or {}
        if current_state.get("current_stage") == "ppt_export":
            stage_key = "ppt_export"
        elif current_state.get("current_stage") == "elements_generation":
            stage_key = "elements_generation"
        elif current_state.get("current_stage") == "planning":
            stage_key = "planning"
        finalize_job_error(
            job_dir,
            job_id,
            stage_key,
            {
                "error": str(exc),
                "job_id": job_id,
                "stage": stage_key,
                "exception_type": exc.__class__.__name__,
                "traceback": traceback.format_exc(),
            },
        )
