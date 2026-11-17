"""Offline trust, deduplication and fail-closed tests for cloud failure alerts."""
import unittest
from copy import deepcopy

from scripts.alert_durable_worker_failure import ISSUE_TITLE, alert, trusted_failure


class FailureAlertTests(unittest.TestCase):
    def setUp(self):
        self.repo = "yabigdd-9/WEBSITE-AUDITOR"
        self.event = {
            "repository": {"full_name": self.repo},
            "workflow_run": {
                "name": "Durable Cloud Draft Pipeline",
                "conclusion": "failure",
                "head_branch": "master",
                "head_repository": {"full_name": self.repo},
                "event": "schedule",
                "id": 123456,
            },
        }
        self.posts = []

    def post(self, path, payload):
        self.posts.append((path, payload))
        return {"number": 88}

    def test_failed_master_run_creates_one_safe_issue(self):
        result = alert(self.event, self.repo, lambda _: [], self.post)
        self.assertEqual(result, {"result": "created", "issue": 88, "run_id": 123456})
        self.assertEqual(len(self.posts), 1)
        path, payload = self.posts[0]
        self.assertEqual(path, f"repos/{self.repo}/issues")
        self.assertEqual(payload["title"], ISSUE_TITLE)
        self.assertIn("https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/123456",
                      payload["body"])
        self.assertIn("\\n- Conclusion: failure\\n", payload["body"])
        self.assertNotIn("password", payload["body"].lower())

    def test_open_issue_is_reused_without_posting(self):
        existing = [{"title": ISSUE_TITLE, "number": 45}]
        result = alert(self.event, self.repo, lambda _: existing, self.post)
        self.assertEqual(result, {"result": "existing", "issue": 45})
        self.assertEqual(self.posts, [])

    def test_pagination_finds_issue_without_creating_duplicate(self):
        calls = []

        def get(path):
            calls.append(path)
            if len(calls) == 1:
                return [{"title": "unrelated", "number": i} for i in range(100)]
            return [{"title": ISSUE_TITLE, "number": 60}]

        self.assertEqual(alert(self.event, self.repo, get, self.post)["issue"], 60)
        self.assertEqual(len(calls), 2)
        self.assertIn("page=2", calls[-1])
        self.assertEqual(self.posts, [])

    def test_ignore_success_skipped_pr_fork_and_unrelated(self):
        cases = [
            ("conclusion", "success"),
            ("conclusion", "skipped"),
            ("name", "Unrelated Workflow"),
            ("head_branch", "feature"),
            ("event", "pull_request"),
        ]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                event = deepcopy(self.event)
                event["workflow_run"][key] = value
                self.assertIsNone(trusted_failure(event, self.repo))
        event = deepcopy(self.event)
        event["workflow_run"]["head_repository"]["full_name"] = "attacker/repo"
        self.assertIsNone(trusted_failure(event, self.repo))
        event = deepcopy(self.event)
        event["repository"]["full_name"] = "attacker/repo"
        self.assertIsNone(trusted_failure(event, self.repo))
        self.assertEqual(self.posts, [])

    def test_monitor_failure_is_reported(self):
        self.event["workflow_run"]["name"] = "Durable Worker Schedule Health"
        self.event["workflow_run"]["event"] = "workflow_dispatch"
        self.assertEqual(trusted_failure(self.event, self.repo)["run_id"], 123456)

    def test_invalid_identifiers_fail_closed(self):
        with self.assertRaises(ValueError):
            trusted_failure(self.event, "../repo")
        for value in (0, -1, True, "123"):
            self.event["workflow_run"]["id"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                trusted_failure(self.event, self.repo)

    def test_issue_listing_errors_do_not_create_incident(self):
        with self.assertRaises(ValueError):
            alert(self.event, self.repo, lambda _: {}, self.post)
        self.assertEqual(self.posts, [])

    def test_no_unbounded_issue_scan_or_spam(self):
        page = [{"title": "other", "number": i} for i in range(100)]
        with self.assertRaises(RuntimeError):
            alert(self.event, self.repo, lambda _: page, self.post)
        self.assertEqual(self.posts, [])


if __name__ == "__main__":
    unittest.main()
