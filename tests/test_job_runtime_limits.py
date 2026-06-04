from __future__ import annotations

import unittest

from ppt_system.web.services.job_runtime_limits import (
    BoundedJobStatusCache,
    resolve_job_status_cache_max_items,
    resolve_job_worker_count,
)


class JobRuntimeLimitsTests(unittest.TestCase):
    def test_bounded_cache_evicts_oldest_entry(self) -> None:
        cache = BoundedJobStatusCache(max_items=2)

        cache["job-1"] = {"job_id": "job-1"}
        cache["job-2"] = {"job_id": "job-2"}
        cache["job-3"] = {"job_id": "job-3"}

        self.assertNotIn("job-1", cache)
        self.assertIn("job-2", cache)
        self.assertIn("job-3", cache)

    def test_bounded_cache_refreshes_recently_read_entry(self) -> None:
        cache = BoundedJobStatusCache(max_items=2)
        cache["job-1"] = {"job_id": "job-1"}
        cache["job-2"] = {"job_id": "job-2"}

        self.assertEqual(cache.get("job-1")["job_id"], "job-1")
        cache["job-3"] = {"job_id": "job-3"}

        self.assertIn("job-1", cache)
        self.assertNotIn("job-2", cache)

    def test_runtime_limits_fall_back_to_positive_defaults(self) -> None:
        config_loader = lambda: {"job_worker_count": "0", "job_status_cache_max_items": "bad"}

        self.assertEqual(resolve_job_worker_count(config_loader), 1)
        self.assertEqual(resolve_job_status_cache_max_items(config_loader), 500)


if __name__ == "__main__":
    unittest.main()
