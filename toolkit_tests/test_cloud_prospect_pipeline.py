import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import cloud_prospect_pipeline as p

CRYPTO_AVAILABLE = importlib.util.find_spec("cryptography") is not None


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        runner_env = patch.dict("os.environ", {"RUNNER_TEMP": str(self.root)})
        runner_env.start()
        self.addCleanup(runner_env.stop)
        self.rows = [dict(domain="example.com", url="https://example.com/")]
        self.state = p.empty_state()

    def run_queue(self, **kwargs):
        return p.process(
            self.state,
            self.rows,
            workspace=self.root,
            now=kwargs.pop("now", 0),
            run_id="run-1",
            robots=kwargs.pop("robots", lambda _: True),
            **kwargs,
        )

    def complete(self, sites, workspace, entries):
        entries.append(dict(run_id="audit-1", findings=[], internal_scope_draft="review"))
        return [dict(status="COMPLETE")]

    @unittest.skipUnless(CRYPTO_AVAILABLE, "Optional vault dependency is not installed")
    def test_idempotent_queue_and_draft_across_checkpoint(self):
        from cryptography.fernet import Fernet

        self.run_queue(audit=self.complete)
        key = Fernet.generate_key().decode()
        path = self.root / "state.enc"
        p.seal(self.state, path, key)
        self.assertNotIn(b"example.com", path.read_bytes())
        self.state = p.unseal(path, key)

        def forbidden(*args):
            self.fail("Duplicate audit")

        result = self.run_queue(now=10000, audit=forbidden)
        self.assertEqual(result["prospects_found"], 1)
        self.assertEqual(result["drafts_ready"], 1)
        self.assertEqual(result["contacts_sent"], 0)
        self.assertEqual(result["confirmed_revenue"], 0)

    def test_failure_recovery_and_exhaustion_redact_errors(self):
        def fail(*args):
            raise RuntimeError("password=secret alice@example.com")

        self.run_queue(audit=fail)
        self.assertEqual(next(iter(self.state["prospects"].values()))["attempts"], 1)
        self.run_queue(now=1, audit=fail)
        self.assertEqual(next(iter(self.state["prospects"].values()))["attempts"], 1)
        self.run_queue(now=3600, audit=fail)
        self.run_queue(now=10800, audit=fail)
        result = self.run_queue(now=50000, audit=fail)
        self.assertEqual(result["audits_failed"], 1)
        self.assertNotIn("secret", json.dumps(self.state))
        for event in self.state["events"]:
            self.assertEqual(
                set(event),
                {"timestamp_utc", "run_id", "entity_id", "action", "status", "sanitized_error"},
            )
            self.assertTrue(event["timestamp_utc"].endswith("+00:00"))

    def test_robots_and_sticky_suppression(self):
        def forbidden(*args):
            self.fail("Audit must be blocked")

        self.run_queue(robots=lambda _: False, audit=forbidden)
        self.assertEqual(self.state["events"][-1]["sanitized_error"], "robots_blocked")
        self.rows[0]["suppressed"] = True
        self.run_queue(now=4000, audit=forbidden)
        self.rows[0]["suppressed"] = False
        self.run_queue(now=8000, audit=forbidden)
        self.assertEqual(next(iter(self.state["prospects"].values()))["status"], "suppressed")

    def test_removed_source_blocks_retry(self):
        self.run_queue(robots=lambda _: False)
        self.rows = []
        self.run_queue(now=4000, audit=self.complete)
        self.assertEqual(next(iter(self.state["prospects"].values()))["status"], "removed")

    def test_cost_and_send_flags_block_before_requests(self):
        with patch.dict(
            "os.environ",
            {
                "MM_PAID_ALLOWED": "1",
                "MM_ALLOW_EXTERNAL_FREE_MODELS": "0",
                "MM_EXTERNAL_SEND_ALLOWED": "0",
            },
        ):
            with self.assertRaises(ValueError):
                p._verify_safety(Path(__file__).resolve().parents[1])
        with patch.dict(
            "os.environ",
            {
                "MM_PAID_ALLOWED": "0",
                "MM_ALLOW_EXTERNAL_FREE_MODELS": "0",
                "MM_EXTERNAL_SEND_ALLOWED": "1",
            },
        ):
            with self.assertRaises(ValueError):
                p._verify_safety(Path(__file__).resolve().parents[1])

    @unittest.skipUnless(CRYPTO_AVAILABLE, "Optional vault dependency is not installed")
    def test_bad_checkpoint_and_capacity_fail_closed(self):
        from cryptography.fernet import Fernet, InvalidToken

        path = self.root / "state.enc"
        key = Fernet.generate_key().decode()
        p.seal(self.state, path, key)
        with self.assertRaises(InvalidToken):
            p.unseal(path, Fernet.generate_key().decode())
        self.state["events"] = [{}] * p.MAX_EVENTS
        with self.assertRaises(ValueError):
            self.run_queue(audit=self.complete)
        self.assertEqual(self.state["prospects"], {})

    def test_three_audit_budget_and_no_incomplete_drafts(self):
        self.rows = [
            dict(domain=f"site{i}.example.com", url=f"https://site{i}.example.com/")
            for i in range(5)
        ]
        calls = []

        def incomplete(sites, workspace, entries):
            calls.append(sites)
            return [dict(status="INCOMPLETE")]

        result = self.run_queue(audit=incomplete)
        self.assertEqual(len(calls), 3)
        self.assertEqual(result["drafts_ready"], 0)
        self.assertEqual(result["retries_pending"], 3)

    @unittest.skipUnless(CRYPTO_AVAILABLE, "Optional vault dependency is not installed")
    def test_main_roundtrip_and_public_output_contains_counts_only(self):
        import contextlib
        import io

        from cryptography.fernet import Fernet

        path = self.root / "state.enc"
        env = {
            "WA_PIPELINE_STATE_KEY": Fernet.generate_key().decode(),
            "MM_PAID_ALLOWED": "0",
            "MM_ALLOW_EXTERNAL_FREE_MODELS": "0",
            "MM_EXTERNAL_SEND_ALLOWED": "0",
        }
        output = io.StringIO()
        # Real CLI, encryption, policy and persistence; deterministic audit adapter.
        with patch.dict("os.environ", env), patch.object(p, "policy_rows", return_value=[]):
            with contextlib.redirect_stdout(output):
                self.assertEqual(p.main(["--state", str(path), "--bootstrap"]), 0)
                self.assertEqual(p.main(["--state", str(path)]), 0)
                self.assertEqual(p.main(["--state", str(path), "--bootstrap"]), 2)
            restored = p.unseal(path, env["WA_PIPELINE_STATE_KEY"])
        self.assertEqual(len(restored["events"]), 2)
        self.assertNotIn(env["WA_PIPELINE_STATE_KEY"], output.getvalue())
        self.assertNotIn("example.com", output.getvalue())

    def test_checkpoint_rejects_symlink_and_source_escape(self):
        target = self.root / "target.enc"
        target.write_bytes(b"private")
        link = self.root / "link.enc"
        link.symlink_to(target)
        with self.assertRaises(ValueError):
            p.private_state_path(link)
        with self.assertRaises(ValueError):
            p.private_state_path(Path("/workspace/escape.enc"))

    def test_source_requires_owner_policy_review(self):
        allowlist = self.root / "clients.txt"
        allowlist.write_text("https://example.com/\n")
        (self.root / "config").mkdir()
        source = self.root / "config" / "cloud-prospects.json"
        source.write_text(json.dumps([{"domain": "example.com"}]))
        with self.assertRaises(ValueError):
            p.policy_rows(self.root)
        source.write_text(
            json.dumps(
                [
                    dict(
                        domain="example.com",
                        public_business=True,
                        audit_authorized=True,
                        terms_reviewed=True,
                    )
                ]
            )
        )
        self.assertEqual(p.policy_rows(self.root)[0]["url"], "https://example.com/")


if __name__ == "__main__":
    unittest.main()
