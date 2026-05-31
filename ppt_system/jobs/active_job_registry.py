from __future__ import annotations

from concurrent.futures import Future
import threading
from typing import Any


_MISSING = object()
_MANAGED_JOBS_LOCK = threading.Lock()
_MANAGED_JOBS: dict[str, Future[Any] | None] = {}


def mark_job_managed(job_id: str) -> None:
    """
    标记任务已由当前进程接管。

    任务从提交到线程池真正开始执行之间存在短暂窗口，
    这时仍需要避免被“孤儿任务恢复”逻辑误判。
    """
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return
    with _MANAGED_JOBS_LOCK:
        _MANAGED_JOBS[normalized_job_id] = None


def bind_job_future(job_id: str, future: Future[Any]) -> None:
    """把线程池 Future 绑定到已接管任务，任务结束后自动清理。"""
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return
    with _MANAGED_JOBS_LOCK:
        _MANAGED_JOBS[normalized_job_id] = future
    future.add_done_callback(lambda completed_future: _release_bound_future(normalized_job_id, completed_future))


def release_job_management(job_id: str) -> None:
    """主动释放任务托管状态，供异常回滚或测试清理使用。"""
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return
    with _MANAGED_JOBS_LOCK:
        _MANAGED_JOBS.pop(normalized_job_id, None)


def is_job_managed(job_id: str) -> bool:
    """
    判断任务是否仍由当前进程管理。

    若 Future 已结束，会在读取时顺带清理，避免状态长期残留。
    """
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return False
    with _MANAGED_JOBS_LOCK:
        managed_future = _MANAGED_JOBS.get(normalized_job_id, _MISSING)
        if managed_future is _MISSING:
            return False
        if managed_future is not None and managed_future.done():
            current_future = _MANAGED_JOBS.get(normalized_job_id, _MISSING)
            if current_future is managed_future:
                _MANAGED_JOBS.pop(normalized_job_id, None)
            return False
        return True


def clear_job_management_registry() -> None:
    """清空托管注册表，供测试隔离使用。"""
    with _MANAGED_JOBS_LOCK:
        _MANAGED_JOBS.clear()


def _release_bound_future(job_id: str, completed_future: Future[Any]) -> None:
    with _MANAGED_JOBS_LOCK:
        current_future = _MANAGED_JOBS.get(job_id, _MISSING)
        if current_future is completed_future:
            _MANAGED_JOBS.pop(job_id, None)
