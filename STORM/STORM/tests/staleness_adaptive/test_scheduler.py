import unittest

from staleness_adaptive.scheduler import StalenessScheduler


class SchedulerTests(unittest.TestCase):
    def test_releases_after_configured_number_of_writes(self):
        scheduler = StalenessScheduler[str]()
        scheduler.buffer_by_writes("refusal-1", "payload", 2)

        scheduler.record_write()
        self.assertEqual(scheduler.pop_ready(now=0), [])
        scheduler.record_write()

        self.assertEqual(scheduler.pop_ready(now=0)[0].payload, "payload")

    def test_releases_after_configured_delay(self):
        scheduler = StalenessScheduler[str]()
        scheduler.buffer_by_time("refusal-1", "payload", 30, now=10)

        self.assertEqual(scheduler.pop_ready(now=39), [])
        self.assertEqual(scheduler.pop_ready(now=40)[0].notification_id, "refusal-1")


if __name__ == "__main__":
    unittest.main()
