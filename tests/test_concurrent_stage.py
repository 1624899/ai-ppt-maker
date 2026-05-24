from __future__ import annotations

import unittest
from concurrent.futures import Future

from ppt_system.concurrent_stage import drain_fail_safe_futures


def resolved_future(result=None, exc: BaseException | None = None) -> Future:
    future: Future = Future()
    if exc is not None:
        future.set_exception(exc)
    else:
        future.set_result(result)
    return future


class ConcurrentStageTests(unittest.TestCase):
    def test_preserves_success_results_even_when_peer_task_fails(self) -> None:
        futures = {
            resolved_future("ok"): "page_1",
            resolved_future(exc=RuntimeError("boom")): "page_2",
        }
        successes: list[tuple[str, str]] = []
        errors: list[tuple[str, str]] = []
        refill_calls = 0

        def refill() -> None:
            nonlocal refill_calls
            refill_calls += 1

        error = drain_fail_safe_futures(
            futures,
            refill=refill,
            on_success=lambda task, result: successes.append((task, result)),
            on_error=lambda task, exc: errors.append((task, str(exc))),
        )

        self.assertIsInstance(error, RuntimeError)
        self.assertEqual(successes, [("page_1", "ok")])
        self.assertEqual(errors, [("page_2", "boom")])
        self.assertEqual(refill_calls, 0)


if __name__ == "__main__":
    unittest.main()
