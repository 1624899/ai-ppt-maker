from __future__ import annotations

import threading
import time
import unittest

from ppt_system.web.services.job_event_bus import JobEventBus


class JobEventBusTests(unittest.TestCase):
    def test_wait_for_job_change_returns_when_job_is_notified(self) -> None:
        bus = JobEventBus()
        initial_version = bus.job_version("job-demo")
        observed: list[int] = []

        def waiter() -> None:
            observed.append(bus.wait_for_job_change("job-demo", initial_version, 1.0))

        thread = threading.Thread(target=waiter)
        thread.start()
        time.sleep(0.05)
        bus.notify_job_changed("job-demo")
        thread.join(timeout=1.0)

        self.assertFalse(thread.is_alive())
        self.assertEqual(observed, [initial_version + 1])

    def test_job_change_also_advances_history_version(self) -> None:
        bus = JobEventBus()
        initial_history_version = bus.history_version()
        bus.notify_job_changed("job-demo")

        self.assertEqual(bus.job_version("job-demo"), 1)
        self.assertEqual(bus.history_version(), initial_history_version + 1)


if __name__ == "__main__":
    unittest.main()
