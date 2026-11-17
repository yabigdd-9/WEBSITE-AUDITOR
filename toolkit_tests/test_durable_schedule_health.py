"""Deterministic, network-free checks for the independent schedule monitor."""

import unittest
from datetime import datetime, timezone, timedelta

from scripts import check_durable_schedule_health as health

REPO = "owner/repo"
TUESDAY = datetime(2026, 11, 17, 11, 0, tzinfo=timezone.utc)
DUE = datetime(2026, 11, 17, 4, 50, tzinfo=timezone.utc)


def sample(run=None, *, jobs=None, artifacts=None):
    run = run or {
        "id": 77,
        "event": "schedule",
        "head_branch": "master",
        "status": "completed",
        "conclusion": "success",
        "created_at": "2026-11-17T05:15:00Z",
    }
    jobs = [{"name": "draft-pipeline", "conclusion": "success"}] if jobs is None else jobs
    artifacts = [
        {"name": "pipeline-state", "size_in_bytes": 1024, "expired": False}
    ] if artifacts is None else artifacts
    seen = []

    def fetch(path):
        seen.append(path)
        if "/workflows/" in path:
            return {"workflow_runs": [run]}
        if "/jobs" in path:
            return {"jobs": jobs}
        if "/artifacts" in path:
            return {"artifacts": artifacts}
        raise AssertionError("Unexpected endpoint " + path)

    return fetch, seen


class DurableScheduleHealthTests(unittest.TestCase):
    def test_due_slot_has_six_hour_grace(self):
        self.assertEqual(health.latest_expected_slot(TUESDAY), DUE)
        just_before_grace = datetime(2026, 11, 17, 10, 49, tzinfo=timezone.utc)
        last_friday = datetime(2026, 11, 13, 4, 50, tzinfo=timezone.utc)
        self.assertEqual(health.latest_expected_slot(just_before_grace), last_friday)
        self.assertEqual(health.latest_expected_slot(TUESDAY + timedelta(days=1)), DUE)

    def test_utc_required(self):
        with self.assertRaises(ValueError):
            health.latest_expected_slot(datetime(2026, 11, 17, 11, 0))
        with self.assertRaises(ValueError):
            health.verify_health(TUESDAY, lambda _: {}, "bad/path/extra")

    def test_success_requires_worker_and_artifact(self):
        fetch, calls = sample()
        result = health.verify_health(TUESDAY, fetch, REPO)
        self.assertEqual(result["due_utc"], DUE.isoformat())
        self.assertEqual(result["run_id"], 77)
        self.assertTrue(result["checkpoint_present"])
        self.assertEqual(len(calls), 3)
        self.assertIn("event=schedule", calls[0])

    def test_missing_scheduled_event_fails_even_if_other_audits_green(self):
        fetch, _ = sample(run={
            "id": 77, "event": "push", "head_branch": "master",
            "status": "completed", "conclusion": "success",
            "created_at": "2026-11-17T05:15:00Z",
        })
        with self.assertRaisesRegex(RuntimeError, "No scheduled"):
            health.verify_health(TUESDAY, fetch, REPO)

    def test_stale_event_and_wrong_branch_fail(self):
        for date, branch in [
            ("2026-11-16T11:00:00Z", "master"),
            ("2026-11-17T05:15:00Z", "feature/test"),
        ]:
            with self.subTest(date=date, branch=branch):
                fetch, _ = sample(run={
                    "id": 77, "event": "schedule", "head_branch": branch,
                    "status": "completed", "conclusion": "success",
                    "created_at": date,
                })
                with self.assertRaisesRegex(RuntimeError, "No scheduled"):
                    health.verify_health(TUESDAY, fetch, REPO)

    def test_queued_failed_or_skipped_worker_fails(self):
        for status, conclusion, jobs in [
            ("in_progress", None, None),
            ("completed", "failure", None),
            ("completed", "success", [{"name": "draft-pipeline", "conclusion": "skipped"}]),
            ("completed", "success", []),
        ]:
            with self.subTest(status=status, conclusion=conclusion, jobs=jobs):
                run = {
                    "id": 77, "event": "schedule", "head_branch": "master",
                    "status": status, "conclusion": conclusion,
                    "created_at": "2026-11-17T05:15:00Z",
                }
                fetch, _ = sample(run=run, jobs=jobs)
                with self.assertRaises(RuntimeError):
                    health.verify_health(TUESDAY, fetch, REPO)

    def test_missing_empty_or_expired_checkpoint_fails(self):
        for artifacts in [
            [], [{"name": "pipeline-state", "size_in_bytes": 0, "expired": False}],
            [{"name": "pipeline-state", "size_in_bytes": 50, "expired": True}],
            [{"name": "public-review", "size_in_bytes": 50, "expired": False}],
        ]:
            with self.subTest(artifacts=artifacts):
                fetch, _ = sample(artifacts=artifacts)
                with self.assertRaisesRegex(RuntimeError, "checkpoint"):
                    health.verify_health(TUESDAY, fetch, REPO)


if __name__ == "__main__":
    unittest.main()
