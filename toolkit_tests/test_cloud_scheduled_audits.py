"""Unit tests for free GitHub scheduled-audit bounded runner."""
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from scripts.cloud_scheduled_audits import load_sites, run


class CloudScheduledAuditsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.allowlist = self.root / "clients.txt"

    def test_explicit_allowlist(self):
        self.allowlist.write_text("# comment\nhttps://example.co.nz\n")
        self.assertEqual(load_sites(self.allowlist), [("example.co.nz", "https://example.co.nz")])

    def test_invalid_targets_rejected(self):
        bad = [
            "http://example.com",
            "https://localhost",
            "https://127.0.0.1",
            "https://example.com/admin",
            "https://example.com?secret=1",
            "https://example.com:8080",
            "https://me:pass@example.com",
        ]
        for url in bad:
            with self.subTest(url=url):
                self.allowlist.write_text(url + "\n")
                with self.assertRaises(ValueError):
                    load_sites(self.allowlist)

    def test_duplicates_rejected(self):
        self.allowlist.write_text("https://example.com\nhttps://example.com\n")
        with self.assertRaises(ValueError):
            load_sites(self.allowlist)

    def test_missing_or_empty_allowlist_rejected(self):
        with self.assertRaises(ValueError):
            load_sites(self.allowlist)
        self.allowlist.write_text("# none\n")
        with self.assertRaises(ValueError):
            load_sites(self.allowlist)

    def test_success_uses_bounded_cli_and_no_other_side_effects(self):
        captured = []
        def fake_runner(command, **kwargs):
            captured.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0, "", "")
        status = run([("example.com", "https://example.com")],
                     output_root=self.root, runner=fake_runner)
        self.assertEqual(status, 0)
        command, options = captured[0]
        self.assertEqual(command[:3], ["wa", "audit", "https://example.com"])
        self.assertIn("--max-pages", command)
        self.assertIn("--max-depth", command)
        self.assertNotIn("--browser", command)
        self.assertEqual(options["timeout"], 150)

    def test_partial_audit_reports_only_required_failed_checks(self):
        report_dir = self.root / "bounded-run"
        report_dir.mkdir()
        report_path = report_dir / "report.json"
        report_path.write_text(json.dumps({
            "status": "partial",
            "checks": {
                "fetch": {"status": "ok", "required": True},
                "tls": {"status": "error", "required": True, "reason": "redacted"},
                "dns": {"status": "error", "required": True, "reason": "do not publish"},
                "browser": {"status": "skipped", "required": False},
            },
        }))
        def fake_runner(command, **kwargs):
            return subprocess.CompletedProcess(command, 2, json.dumps([{
                "status": "partial", "artifacts": {"json": str(report_path)}
            }]), "sensitive failure text")

        captured = StringIO()
        with redirect_stdout(captured):
            result = run([("example.com", "https://example.com")],
                         output_root=self.root, runner=fake_runner)
        self.assertEqual(result, 1)
        output = captured.getvalue()
        self.assertIn("FAIL (partial: dns, tls)", output)
        self.assertNotIn("sensitive failure", output)
        self.assertNotIn("do not publish", output)
        self.assertNotIn("redacted", output)

    def test_partial_report_outside_tmp_dir_is_not_read(self):
        with tempfile.TemporaryDirectory() as outside_dir:
            outside = Path(outside_dir) / "report.json"
            outside.write_text(json.dumps({
                "status": "partial",
                "checks": {"untrusted": {"status": "error", "required": True}},
            }))
            def fake_runner(command, **kwargs):
                return subprocess.CompletedProcess(command, 2, json.dumps([{
                    "status": "partial", "artifacts": {"json": str(outside)}
                }]), "")
            captured = StringIO()
            with redirect_stdout(captured):
                result = run([("example.com", "https://example.com")],
                             output_root=self.root, runner=fake_runner)
            self.assertEqual(result, 1)
            self.assertIn("FAIL (exit 2)", captured.getvalue())
            self.assertNotIn("untrusted", captured.getvalue())

    def test_nonzero_exit_fails_job(self):
        def fake_runner(command, **kwargs):
            return subprocess.CompletedProcess(command, 2, "", "")
        self.assertEqual(run([("example.com", "https://example.com")],
                             output_root=self.root, runner=fake_runner), 1)

    def test_timeout_fails_job(self):
        def fake_runner(command, **kwargs):
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        self.assertEqual(run([("example.com", "https://example.com")],
                             output_root=self.root, runner=fake_runner), 1)


if __name__ == "__main__":
    unittest.main()
