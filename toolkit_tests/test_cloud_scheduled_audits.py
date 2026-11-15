"""Unit tests for free GitHub scheduled-audit bounded runner."""
from pathlib import Path
import subprocess
import tempfile
import unittest

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
