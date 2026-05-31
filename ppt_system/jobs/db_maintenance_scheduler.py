from __future__ import annotations

import atexit
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


DEFAULT_DB_MAINTENANCE_CONFIG = {
    "enabled": False,
    "interval_seconds": 3600,
    "keep_latest": 20,
    "include_pinned": False,
    "vacuum": True,
    "min_reclaimable_bytes": 8 * 1024 * 1024,
}


@dataclass(slots=True)
class JobDbMaintenanceScheduler:
    db_path: Path
    config_loader: Callable[[], dict[str, Any]]
    maintenance_runner: Callable[..., dict[str, Any]]
    stats_collector: Callable[[Path], dict[str, Any]]
    running_jobs_counter: Callable[[], int]
    sleep_interval_seconds: float = 5.0
    _thread: threading.Thread | None = None
    _stop_event: threading.Event | None = None
    _wake_event: threading.Event | None = None
    _last_run_started_at: float = 0.0
    _last_result: dict[str, Any] | None = None
    _lock: threading.Lock | None = None

    def __post_init__(self) -> None:
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._wake_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="job-db-maintenance",
                daemon=True,
            )
            self._thread.start()
        atexit.register(self.stop)

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()

    def trigger_now(self) -> None:
        self._wake_event.set()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            last_result = self._last_result
            last_run_started_at = self._last_run_started_at
        return {
            "running": bool(self._thread and self._thread.is_alive()),
            "last_run_started_at": last_run_started_at,
            "last_result": last_result,
        }

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            config = resolve_job_db_maintenance_config(self.config_loader())
            if not config["enabled"]:
                self._wait(self.sleep_interval_seconds)
                continue
            now = time.time()
            last_started_at = self._last_run_started_at
            due = last_started_at <= 0 or (now - last_started_at) >= float(config["interval_seconds"])
            if due:
                self._execute_once(config)
                continue
            remaining = max(1.0, float(config["interval_seconds"]) - (now - last_started_at))
            self._wait(min(remaining, self.sleep_interval_seconds))

    def _wait(self, timeout_seconds: float) -> None:
        self._wake_event.wait(timeout=max(0.1, float(timeout_seconds)))
        self._wake_event.clear()

    def _execute_once(self, config: dict[str, Any]) -> None:
        with self._lock:
            self._last_run_started_at = time.time()
        if self.running_jobs_counter() > 0:
            self._store_result(
                {
                    "status": "skipped",
                    "reason": "running_jobs",
                    "running_job_count": self.running_jobs_counter(),
                }
            )
            self._wait(self.sleep_interval_seconds)
            return
        stats = self.stats_collector(self.db_path)
        candidate_cleanup = stats.get("job_count", 0) > int(config["keep_latest"])
        candidate_vacuum = bool(config["vacuum"]) and int(stats.get("reclaimable_bytes", 0)) >= int(config["min_reclaimable_bytes"])
        if not candidate_cleanup and not candidate_vacuum:
            self._store_result(
                {
                    "status": "skipped",
                    "reason": "not_needed",
                    "stats": stats,
                }
            )
            self._wait(self.sleep_interval_seconds)
            return
        result = self.maintenance_runner(
            self.db_path,
            keep_latest=int(config["keep_latest"]),
            include_pinned=bool(config["include_pinned"]),
            dry_run=False,
            vacuum=bool(config["vacuum"]),
        )
        self._store_result(
            {
                "status": "completed",
                "config": config,
                "result": result,
            }
        )

    def _store_result(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._last_result = payload


def resolve_job_db_maintenance_config(config: dict[str, Any] | None) -> dict[str, Any]:
    source = config or {}
    merged = dict(DEFAULT_DB_MAINTENANCE_CONFIG)
    merged["enabled"] = bool(source.get("job_db_maintenance_enabled", merged["enabled"]))
    merged["interval_seconds"] = max(60, int(source.get("job_db_maintenance_interval_seconds", merged["interval_seconds"])))
    merged["keep_latest"] = max(0, int(source.get("job_db_maintenance_keep_latest", merged["keep_latest"])))
    merged["include_pinned"] = bool(source.get("job_db_maintenance_include_pinned", merged["include_pinned"]))
    merged["vacuum"] = bool(source.get("job_db_maintenance_vacuum", merged["vacuum"]))
    merged["min_reclaimable_bytes"] = max(
        0,
        int(source.get("job_db_maintenance_min_reclaimable_bytes", merged["min_reclaimable_bytes"])),
    )
    return merged
