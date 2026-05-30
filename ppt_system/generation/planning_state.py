from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def _read_page_prompt(page: Mapping[str, Any]) -> str:
    """读取页面上可用于首阶段原稿图生成的提示词。"""
    for key in ("reference_prompt", "image_prompt", "prompt"):
        value = str(page.get(key, "")).strip()
        if value:
            return value
    return ""


def has_complete_page_plan(
    pages: Sequence[Mapping[str, Any]],
    expected_count: int | None = None,
) -> bool:
    """判断页面规划是否完整可恢复。"""
    normalized_pages = list(pages or [])
    if not normalized_pages:
        return False

    if expected_count is not None and expected_count > 0 and len(normalized_pages) != expected_count:
        return False

    page_numbers: set[int] = set()
    for page in normalized_pages:
        if not isinstance(page, Mapping):
            return False
        page_no = int(page.get("page_no", 0) or 0)
        if page_no <= 0 or page_no in page_numbers:
            return False
        page_numbers.add(page_no)
        if not _read_page_prompt(page):
            return False

    return True


def has_complete_planning_state(state: Mapping[str, Any]) -> bool:
    """判断任务状态中的规划结果是否足够支撑继续执行。"""
    job_meta = state.get("job_meta", {})
    raw_expected_count = int(job_meta.get("page_count", 0) or 0)
    expected_count = raw_expected_count if raw_expected_count > 0 else None
    pages = state.get("pages", [])
    if not isinstance(pages, Sequence) or isinstance(pages, (str, bytes)):
        return False
    return has_complete_page_plan(pages, expected_count)
