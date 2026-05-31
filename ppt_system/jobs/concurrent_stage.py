from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, wait
from typing import Any, Callable, TypeVar


TaskT = TypeVar("TaskT")
ResultT = TypeVar("ResultT")


def drain_fail_safe_futures(
    futures: dict[Future[ResultT], TaskT],
    *,
    refill: Callable[[], None],
    on_success: Callable[[TaskT, ResultT], None],
    on_error: Callable[[TaskT, BaseException], None],
) -> BaseException | None:
    first_error: BaseException | None = None
    while futures:
        done, _ = wait(list(futures.keys()), return_when=FIRST_COMPLETED)
        for future in done:
            task = futures.pop(future)
            try:
                result = future.result()
            except BaseException as exc:
                on_error(task, exc)
                if first_error is None:
                    first_error = exc
                continue
            on_success(task, result)

        # 只有当前一批全部成功时才继续补充新任务，避免失败后继续扩大调用量。
        if first_error is None:
            refill()

    return first_error
