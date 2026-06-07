from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ppt_system.web.services.job_state_runtime import append_stage_log, update_page_state


def submit_reference_task(
    executor: ThreadPoolExecutor,
    job_dir: Path,
    job_id: str,
    page: dict[str, Any],
    stage1_dir: Path,
    image_provider: Any,
    style_reference_paths: list[Path],
    reference_mode: str = "generation",
) -> tuple[Any, int, str, Path]:
    page_no = int(page["page_no"])
    prompt = str(page["image_prompt"]).strip()
    if not prompt:
        raise ValueError(f"第 {page_no} 页缺少原稿图提示词，需重新执行规划阶段")
    image_path = stage1_dir / f"page_{page_no:02d}_reference.png"
    prompt_path = stage1_dir / f"page_{page_no:02d}_reference_prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    update_page_state(job_dir, job_id, page_no, status="rendering_reference", reference_prompt=prompt)
    append_stage_log(job_dir, job_id, "reference_generation", f"第 {page_no} 页已进入原稿图生成队列")
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
    reference_page_path: Path,
    stage2_dir: Path,
    image_provider: Any,
) -> tuple[Any, int, Path]:
    out_path = stage2_dir / f"page_{page_no:02d}_elements.png"
    prompt_path = stage2_dir / f"page_{page_no:02d}_elements_prompt.txt"
    prompt_path.write_text(elements_prompt, encoding="utf-8")
    update_page_state(job_dir, job_id, page_no, status="rendering_elements", elements_prompt=elements_prompt)
    append_stage_log(job_dir, job_id, "elements_generation", f"第 {page_no} 页元素图已进入并发队列")
    future = executor.submit(image_provider.generate_elements_page, elements_prompt, reference_page_path, out_path)
    return future, page_no, out_path
