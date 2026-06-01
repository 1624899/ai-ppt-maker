from __future__ import annotations

import threading
import time

from ppt_system.runtime.interruptible_execution import run_interruptible_call


def test_interruptible_call_returns_completed_result() -> None:
    assert run_interruptible_call(
        lambda: "ok",
        stop_checker=lambda: False,
        interruption_message="已中断",
    ) == "ok"


def test_interruptible_call_stops_waiting_for_slow_call() -> None:
    started = threading.Event()
    stop_requested = threading.Event()

    def slow_call() -> str:
        started.set()
        time.sleep(10)
        return "too-late"

    def should_stop() -> bool:
        return stop_requested.is_set()

    interrupter = threading.Thread(
        target=lambda: (started.wait(2), stop_requested.set()),
        daemon=True,
    )
    interrupter.start()

    started_at = time.monotonic()
    try:
        run_interruptible_call(
            slow_call,
            stop_checker=should_stop,
            interruption_message="已中断",
            poll_interval_seconds=0.05,
        )
    except InterruptedError:
        elapsed = time.monotonic() - started_at
        assert elapsed < 1.0
    else:
        raise AssertionError("预期长调用会被中断")
