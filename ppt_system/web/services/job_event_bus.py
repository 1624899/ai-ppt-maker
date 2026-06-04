from __future__ import annotations

import threading
from collections import defaultdict


class JobEventBus:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._job_versions: dict[str, int] = defaultdict(int)
        self._history_version = 0

    def notify_job_changed(self, job_id: str) -> None:
        normalized_job_id = str(job_id or "").strip()
        with self._condition:
            if normalized_job_id:
                self._job_versions[normalized_job_id] += 1
            self._history_version += 1
            self._condition.notify_all()

    def notify_history_changed(self) -> None:
        with self._condition:
            self._history_version += 1
            self._condition.notify_all()

    def job_version(self, job_id: str) -> int:
        with self._condition:
            return int(self._job_versions.get(str(job_id or "").strip(), 0))

    def history_version(self) -> int:
        with self._condition:
            return self._history_version

    def wait_for_job_change(self, job_id: str, last_version: int, timeout: float) -> int:
        normalized_job_id = str(job_id or "").strip()

        def changed() -> bool:
            return int(self._job_versions.get(normalized_job_id, 0)) != last_version

        with self._condition:
            self._condition.wait_for(changed, timeout=max(0.0, float(timeout)))
            return int(self._job_versions.get(normalized_job_id, 0))

    def wait_for_history_change(self, last_version: int, timeout: float) -> int:
        def changed() -> bool:
            return self._history_version != last_version

        with self._condition:
            self._condition.wait_for(changed, timeout=max(0.0, float(timeout)))
            return self._history_version


JOB_EVENT_BUS = JobEventBus()
