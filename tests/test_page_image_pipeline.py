from __future__ import annotations

import unittest
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from ppt_system.generation.page_image_pipeline import run_page_image_pipeline


def resolved_future(result: Any = None, exc: BaseException | None = None) -> Future:
    future: Future = Future()
    if exc is not None:
        future.set_exception(exc)
    else:
        future.set_result(result)
    return future


class PageImagePipelineTests(unittest.TestCase):
    def test_starts_elements_when_each_reference_finishes(self) -> None:
        events: list[str] = []

        def submit_reference(_: ThreadPoolExecutor, page: dict[str, int]):
            page_no = int(page["page_no"])
            events.append(f"ref_submit_{page_no}")
            return resolved_future({"kind": "ref", "page_no": page_no}), ("page", page_no, "", None)

        def submit_elements(_: ThreadPoolExecutor, page_no: int):
            events.append(f"elem_submit_{page_no}")
            return resolved_future({"kind": "elem", "page_no": page_no}), (page_no, None)

        result = run_page_image_pipeline(
            pending_reference_pages=[{"page_no": 1}, {"page_no": 2}],
            pending_element_page_numbers=[],
            reference_concurrency=1,
            element_concurrency=1,
            enable_elements=True,
            get_page_no=lambda page: int(page["page_no"]),
            submit_reference=submit_reference,
            submit_elements=submit_elements,
            on_reference_success=lambda task, meta: events.append(f"ref_done_{task[1]}"),
            on_reference_error=lambda task, exc: events.append(f"ref_error_{task[1]}"),
            on_elements_success=lambda task, meta: events.append(f"elem_done_{task[0]}"),
            on_elements_error=lambda task, exc: events.append(f"elem_error_{task[0]}"),
            should_stop=lambda: False,
            on_stop=lambda stage: events.append(f"stop_{stage}"),
        )

        self.assertIsNone(result.first_error)
        self.assertLess(events.index("elem_submit_1"), events.index("ref_submit_2"))
        self.assertIn("elem_done_1", events)
        self.assertIn("elem_done_2", events)

    def test_does_not_expand_elements_after_reference_failure(self) -> None:
        events: list[str] = []

        def submit_reference(_: ThreadPoolExecutor, page: dict[str, int]):
            page_no = int(page["page_no"])
            events.append(f"ref_submit_{page_no}")
            if page_no == 1:
                return resolved_future(exc=RuntimeError("boom")), ("page", page_no, "", None)
            return resolved_future({"kind": "ref", "page_no": page_no}), ("page", page_no, "", None)

        def submit_elements(_: ThreadPoolExecutor, page_no: int):
            events.append(f"elem_submit_{page_no}")
            return resolved_future({"kind": "elem", "page_no": page_no}), (page_no, None)

        result = run_page_image_pipeline(
            pending_reference_pages=[{"page_no": 1}, {"page_no": 2}],
            pending_element_page_numbers=[],
            reference_concurrency=2,
            element_concurrency=1,
            enable_elements=True,
            get_page_no=lambda page: int(page["page_no"]),
            submit_reference=submit_reference,
            submit_elements=submit_elements,
            on_reference_success=lambda task, meta: events.append(f"ref_done_{task[1]}"),
            on_reference_error=lambda task, exc: events.append(f"ref_error_{task[1]}"),
            on_elements_success=lambda task, meta: events.append(f"elem_done_{task[0]}"),
            on_elements_error=lambda task, exc: events.append(f"elem_error_{task[0]}"),
            should_stop=lambda: False,
            on_stop=lambda stage: events.append(f"stop_{stage}"),
        )

        self.assertIsInstance(result.reference_error, RuntimeError)
        self.assertNotIn("elem_submit_2", events)


if __name__ == "__main__":
    unittest.main()
