from __future__ import annotations

import os
import queue
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any, TypeVar


StopChecker = Callable[[], bool]
T = TypeVar("T")

DEFAULT_POLL_INTERVAL_SECONDS = 0.2


def run_interruptible_call(
    call: Callable[[], T],
    *,
    stop_checker: StopChecker | None,
    interruption_message: str,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> T:
    if stop_checker is None:
        return call()
    if stop_checker():
        raise InterruptedError(interruption_message)

    result_queue: queue.Queue[tuple[bool, T | BaseException]] = queue.Queue(maxsize=1)

    def worker() -> None:
        try:
            result_queue.put((True, call()))
        except BaseException as exc:
            result_queue.put((False, exc))

    thread = threading.Thread(target=worker, name="interruptible-call", daemon=True)
    thread.start()
    poll_interval = max(0.05, float(poll_interval_seconds))

    while True:
        try:
            succeeded, value = result_queue.get(timeout=poll_interval)
        except queue.Empty:
            if stop_checker():
                raise InterruptedError(interruption_message)
            continue

        if stop_checker():
            raise InterruptedError(interruption_message)
        if succeeded:
            return value  # type: ignore[return-value]
        raise value


def run_interruptible_process(
    command: Sequence[str],
    *,
    timeout_seconds: float | None = None,
    stop_checker: StopChecker | None = None,
    interruption_message: str,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    popen_kwargs: dict[str, Any] | None = None,
) -> subprocess.CompletedProcess[Any]:
    kwargs = dict(popen_kwargs or {})
    if os.name != "nt" and "start_new_session" not in kwargs:
        kwargs["start_new_session"] = True

    process = subprocess.Popen(list(command), **kwargs)
    started_at = time.monotonic()
    poll_interval = max(0.05, float(poll_interval_seconds))

    try:
        while True:
            communicate_timeout = poll_interval
            if timeout_seconds is not None:
                elapsed = time.monotonic() - started_at
                remaining = float(timeout_seconds) - elapsed
                if remaining <= 0:
                    stdout, stderr = terminate_process(process)
                    raise subprocess.TimeoutExpired(
                        process.args,
                        timeout_seconds,
                        output=stdout,
                        stderr=stderr,
                    )
                communicate_timeout = min(poll_interval, remaining)

            try:
                stdout, stderr = process.communicate(timeout=communicate_timeout)
            except subprocess.TimeoutExpired:
                if stop_checker and stop_checker():
                    stdout, stderr = terminate_process(process)
                    raise InterruptedError(interruption_message)
                continue

            if stop_checker and stop_checker():
                raise InterruptedError(interruption_message)
            return subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
    except BaseException:
        if process.poll() is None:
            terminate_process(process)
        raise


def terminate_process(process: subprocess.Popen[Any]) -> tuple[Any, Any]:
    if process.poll() is None:
        _terminate_process_tree(process)
    try:
        return process.communicate(timeout=1.0)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.communicate()


def _terminate_process_tree(process: subprocess.Popen[Any]) -> None:
    if os.name == "nt":
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                creationflags=creation_flags,
            )
            return
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            return
        except OSError:
            pass
    process.terminate()
