from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Any, Callable, TypeVar


PageT = TypeVar("PageT")
RefTaskT = TypeVar("RefTaskT")
ElemTaskT = TypeVar("ElemTaskT")


@dataclass(frozen=True)
class PageImagePipelineResult:
    reference_error: BaseException | None = None
    elements_error: BaseException | None = None
    stopped_stage: str | None = None

    @property
    def first_error(self) -> BaseException | None:
        return self.reference_error or self.elements_error


def run_page_image_pipeline(
    *,
    pending_reference_pages: list[PageT],
    pending_element_page_numbers: list[int],
    reference_concurrency: int,
    element_concurrency: int,
    enable_elements: bool,
    get_page_no: Callable[[PageT], int],
    submit_reference: Callable[[ThreadPoolExecutor, PageT], tuple[Future[Any], RefTaskT]],
    submit_elements: Callable[[ThreadPoolExecutor, int], tuple[Future[Any], ElemTaskT]],
    on_reference_success: Callable[[RefTaskT, Any], None],
    on_reference_error: Callable[[RefTaskT, BaseException], None],
    on_elements_success: Callable[[ElemTaskT, Any], None],
    on_elements_error: Callable[[ElemTaskT, BaseException], None],
    should_stop: Callable[[], bool],
    on_stop: Callable[[str], None],
) -> PageImagePipelineResult:
    """按页串接原稿图与元素图，让已完成原稿图尽早进入元素图阶段。"""
    reference_limit = max(1, int(reference_concurrency))
    element_limit = max(1, int(element_concurrency))
    pending_references = list(pending_reference_pages)
    pending_elements = list(dict.fromkeys(int(page_no) for page_no in pending_element_page_numbers))
    queued_element_pages = set(pending_elements)
    blocked_element_pages: set[int] = {get_page_no(page) for page in pending_references}
    reference_futures: dict[Future[Any], RefTaskT] = {}
    element_futures: dict[Future[Any], ElemTaskT] = {}
    reference_error: BaseException | None = None
    elements_error: BaseException | None = None
    stopped_stage: str | None = None

    def submit_ready_references(executor: ThreadPoolExecutor) -> None:
        nonlocal stopped_stage
        if stopped_stage or reference_error is not None:
            return
        if should_stop():
            stopped_stage = "reference_generation"
            on_stop(stopped_stage)
            return
        while pending_references and len(reference_futures) < reference_limit:
            page = pending_references.pop(0)
            future, task = submit_reference(executor, page)
            reference_futures[future] = task

    def submit_ready_elements(executor: ThreadPoolExecutor) -> None:
        nonlocal stopped_stage
        if not enable_elements or stopped_stage or reference_error is not None or elements_error is not None:
            return
        if should_stop():
            stopped_stage = "elements_generation"
            on_stop(stopped_stage)
            return
        while pending_elements and len(element_futures) < element_limit:
            page_no = int(pending_elements[0])
            if page_no in blocked_element_pages:
                break
            pending_elements.pop(0)
            future, task = submit_elements(executor, page_no)
            element_futures[future] = task

    def wait_for_any() -> list[Future[Any]]:
        active = list(reference_futures.keys()) + list(element_futures.keys())
        if not active:
            return []
        done, _ = wait(active, return_when=FIRST_COMPLETED)
        return list(done)

    with ThreadPoolExecutor(max_workers=reference_limit) as reference_executor:
        with ThreadPoolExecutor(max_workers=element_limit) as element_executor:
            submit_ready_references(reference_executor)
            submit_ready_elements(element_executor)

            while reference_futures or element_futures:
                for future in wait_for_any():
                    if future in reference_futures:
                        task = reference_futures.pop(future)
                        try:
                            result = future.result()
                        except BaseException as exc:
                            on_reference_error(task, exc)
                            if reference_error is None:
                                reference_error = exc
                            continue
                        on_reference_success(task, result)
                        page_no = _resolve_task_page_no(task)
                        blocked_element_pages.discard(page_no)
                        if enable_elements and page_no not in queued_element_pages:
                            pending_elements.append(page_no)
                            queued_element_pages.add(page_no)
                        continue

                    task = element_futures.pop(future)
                    try:
                        result = future.result()
                    except BaseException as exc:
                        on_elements_error(task, exc)
                        if elements_error is None:
                            elements_error = exc
                        continue
                    on_elements_success(task, result)

                submit_ready_elements(element_executor)
                submit_ready_references(reference_executor)

    return PageImagePipelineResult(
        reference_error=reference_error,
        elements_error=elements_error,
        stopped_stage=stopped_stage,
    )


def _resolve_task_page_no(task: Any) -> int:
    if isinstance(task, tuple) and len(task) >= 2:
        return int(task[1])
    if isinstance(task, dict):
        return int(task["page_no"])
    return int(getattr(task, "page_no"))
