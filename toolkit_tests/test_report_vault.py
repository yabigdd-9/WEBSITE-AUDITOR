"""Offline validation for optional encrypted reports in public Actions.

These tests generate temporary keys. They never use or print an owner's key.
"""
import base64
import importlib.util
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts import report_vault
from scripts.cloud_review_only_opportunities import (
    main as review_main,
    run_review_sites,
)
from toolkit_tests.test_cloud_review_only_opportunities import sample_report

CRYPTO_AVAILABLE = importlib.util.find_spec("cryptography") is not None


@unittest.skipUnless(CRYPTO_AVAILABLE, "Optional vault dependency is not installed")
class EncryptedReportVaultTests(unittest.TestCase):
    def test_round_trip_and_no_plaintext_leak(self):
        private, public = report_vault.new_keypair()
        report = {
            "kind": "private_report",
            "site": "https://example.com",
            "observed": "private evidence for owner, never publish",
            "contact": None,
        }
        blob = report_vault.encrypt_document(report, public)
        self.assertNotIn(report["observed"].encode(), blob)
        envelope = json.loads(blob)
        self.assertEqual(envelope["format"], report_vault.FORMAT)
        self.assertEqual(report_vault.decrypt_document(blob, private), report)

    def test_unauthorized_key_and_modified_ciphertext_fail(self):
        private, public = report_vault.new_keypair()
        stranger, _ = report_vault.new_keypair()
        blob = report_vault.encrypt_document({"confidential": 123}, public)
        with self.assertRaises(Exception):
            report_vault.decrypt_document(blob, stranger)
        payload = json.loads(blob)
        raw = bytearray(base64.b64decode(payload["ciphertext"]))
        raw[-1] ^= 0x10
        payload["ciphertext"] = base64.b64encode(raw).decode()
        with self.assertRaises(Exception):
            report_vault.decrypt_document(json.dumps(payload).encode(), private)

    def test_malformed_key_and_oversized_document_are_rejected(self):
        _, public = report_vault.new_keypair()
        with self.assertRaises(ValueError):
            report_vault.encrypt_document({}, "not a key")
        with self.assertRaises(ValueError):
            report_vault.encrypt_document({"huge": "a" * 1_000_010}, public)

    def test_keygen_writes_private_only_to_new_restricted_local_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "owner.key"
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(report_vault.main(["keygen", "--private-out", str(path)]), 0)
            private = path.read_text().strip()
            self.assertNotIn(private, output.getvalue())
            self.assertEqual(path.stat().st_mode & 0o077, 0)
            with self.assertRaises(FileExistsError):
                report_vault.main(["keygen", "--private-out", str(path)])

    def test_allowlisted_review_reports_are_bounded_and_private(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with patch(
                "scripts.cloud_review_only_opportunities.run_audit",
                return_value=sample_report(),
            ):
                entries = []
                rows = run_review_sites(
                    [("example.com", "https://example.com")], root, entries
                )
            self.assertEqual(rows[0]["status"], "COMPLETE")
            self.assertEqual(len(entries), 1)
            entry = entries[0]
            self.assertEqual(entry["domain"], "example.com")
            self.assertEqual(len(entry["findings"]), 1)
            self.assertIn("DO NOT SEND", entry["internal_scope_draft"])
            self.assertNotIn("contacts", entry)
            self.assertEqual(entry["outbound_sent"], 0)

    def test_encryption_is_opt_in_and_only_on_non_pr_runs(self):
        private, public = report_vault.new_keypair()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            allowlist = root / "clients.txt"
            allowlist.write_text("https://example.com\n")
            out = root / "sealed.json"
            env = {
                "MM_PAID_ALLOWED": "0",
                "MM_ALLOW_EXTERNAL_FREE_MODELS": "0",
                "MM_EXTERNAL_SEND_ALLOWED": "0",
                "MM_REPORT_PUBLIC_KEY_B64": public,
                "MM_ENCRYPTED_REPORT_OUT": str(out),
                "RUNNER_TEMP": str(root),
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_STEP_SUMMARY": str(root / "unit-test-summary.md"),
            }
            with patch.dict(os.environ, env):
                with patch(
                    "scripts.cloud_review_only_opportunities.run_audit",
                    return_value=sample_report(),
                ):
                    with redirect_stdout(StringIO()):
                        self.assertEqual(
                            review_main(["--allowlist", str(allowlist), "--all"]), 0
                        )
                self.assertFalse(out.exists())
                os.environ["GITHUB_EVENT_NAME"] = "push"
                with patch(
                    "scripts.cloud_review_only_opportunities.run_audit",
                    return_value=sample_report(),
                ):
                    with redirect_stdout(StringIO()):
                        self.assertEqual(
                            review_main(["--allowlist", str(allowlist), "--all"]), 0
                        )
            self.assertTrue(out.exists())
            content = report_vault.decrypt_document(out.read_bytes(), private)
            self.assertEqual(content["external_sends"], 0)
            self.assertEqual(content["paid_calls"], 0)
            self.assertEqual(len(content["sites"]), 1)
            self.assertIn("DO NOT SEND", content["sites"][0]["internal_scope_draft"])


if __name__ == "__main__":
    unittest.main()
