from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from typing import Any


DEFAULT_JOB_WORKER_COUNT = 2
DEFAULT_JOB_STATUS_CACHE_MAX_ITEMS = 500


class BoundedJobStatusCache(OrderedDict[str, dict[str, Any]]):
    def __init__(self, max_items: int = DEFAULT_JOB_STATUS_CACHE_MAX_ITEMS) -> None:
        super().__init__()
        self.max_items = max(1, int(max_items))

    def __setitem__(self, key: str, value: dict[str, Any]) -> None:
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        self._trim()

    def get(self, key: str, default: Any = None) -> Any:
        if key not in self:
            return default
        self.move_to_end(key)
        return super().__getitem__(key)

    def _trim(self) -> None:
        while len(self) > self.max_items:
            self.popitem(last=False)


def resolve_job_worker_count(config_loader: Callable[[], dict[str, Any]]) -> int:
    config = _safe_load_config(config_loader)
    return _bounded_positive_int(config.get("job_worker_count"), default=DEFAULT_JOB_WORKER_COUNT)


def resolve_job_status_cache_max_items(config_loader: Callable[[], dict[str, Any]]) -> int:
    config = _safe_load_config(config_loader)
    return _bounded_positive_int(
        config.get("job_status_cache_max_items"),
        default=DEFAULT_JOB_STATUS_CACHE_MAX_ITEMS,
    )


def _safe_load_config(config_loader: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        config = config_loader()
    except Exception:
        return {}
    return config if isinstance(config, dict) else {}


def _bounded_positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(default)
    return max(1, parsed)
