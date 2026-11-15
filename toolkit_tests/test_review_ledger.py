"""Network-free privacy, dedupe and lifecycle tests for the local review ledger."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from scripts import review_ledger


def fixture(run_id="run-001", at="2026-11-15T00:00:00Z", findings=True):
    return {
        "schema_version": 1,
        "kind": "website_auditor_encrypted_review_bundle",
        "allowlist_only": True,
        "owner_review_required": True,
        "external_sends": 0,
        "paid_calls": 0,
        "sites": [{
            "domain": "example.co.nz",
            "status": "COMPLETE",
            "run_id": run_id,
            "timestamp": at,
            "findings": ([{
                "finding_id": "finding-001",
                "defect_key": "missing_title",
                "severity": "high",
                "observed": "No title found at test site",
                "remediation_action": "Review a page title",
            }] if findings else []),
            "internal_scope_draft": (
                "INTERNAL SCOPE DRAFT - DO NOT SEND\n"
                "Example concept based on captured site evidence."
                if findings else None
            ),
            "approval_status": "HUMAN_REVIEW_REQUIRED",
            "outbound_sent": 0,
        }],
    }


class ReviewLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dbpath = self.root / "review.sqlite3"

    def test_first_import_creates_private_database_and_review_only_draft(self):
        counts = review_ledger.import_bundle(fixture(), self.dbpath)
        self.assertEqual(counts["new_runs"], 1)
        self.assertEqual(counts["new_findings"], 1)
        self.assertEqual(counts["internal_drafts"], 1)
        self.assertEqual(self.dbpath.stat().st_mode & 0o077, 0)
        self.assertEqual(review_ledger.summarize(self.dbpath), {
            "sites": 1, "distinct_runs": 1, "distinct_findings": 1,
            "pending_review": 1, "internal_drafts": 1,
        })
        with sqlite3.connect(self.dbpath) as db:
            draft = db.execute(
                "SELECT approval_state,sent FROM internal_drafts"
            ).fetchone()
            self.assertEqual(draft, ("HUMAN_REVIEW_REQUIRED", 0))
            tables = [x[0] for x in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )]
            self.assertFalse({"outreach", "contacts", "revenue", "payments"} & set(tables))

    def test_same_archive_is_idempotent(self):
        first = fixture()
        review_ledger.import_bundle(first, self.dbpath)
        again = review_ledger.import_bundle(first, self.dbpath)
        self.assertTrue(again["duplicate_archive"])
        self.assertEqual(again["new_runs"], 0)
        with sqlite3.connect(self.dbpath) as db:
            self.assertEqual(
                db.execute("SELECT observed_scans FROM findings").fetchone()[0], 1
            )

    def test_distinct_repeat_run_refreshes_observed_finding_not_new_business(self):
        review_ledger.import_bundle(fixture(), self.dbpath)
        review_ledger.import_bundle(
            fixture(run_id="run-002", at="2026-11-16T00:00:00Z"), self.dbpath
        )
        report = review_ledger.summarize(self.dbpath)
        self.assertEqual(report["sites"], 1)
        self.assertEqual(report["distinct_runs"], 2)
        self.assertEqual(report["distinct_findings"], 1)
        self.assertEqual(report["internal_drafts"], 2)
        with sqlite3.connect(self.dbpath) as db:
            self.assertEqual(
                db.execute("SELECT observed_scans FROM findings").fetchone()[0], 2
            )

    def test_absence_does_not_mean_verified_fixed(self):
        review_ledger.import_bundle(fixture(), self.dbpath)
        review_ledger.import_bundle(
            fixture(run_id="run-002", at="2026-11-16T00:00:00Z", findings=False),
            self.dbpath
        )
        with sqlite3.connect(self.dbpath) as db:
            state, times = db.execute(
                "SELECT review_state,observed_scans FROM findings"
            ).fetchone()
        self.assertEqual((state, times), ("PENDING_REVIEW", 1))

    def test_incomplete_scan_does_not_change_current_data(self):
        review_ledger.import_bundle(fixture(), self.dbpath)
        incomplete = fixture(run_id="run-002", findings=False)
        incomplete["sites"][0]["status"] = "INCOMPLETE"
        self.assertEqual(
            review_ledger.import_bundle(incomplete, self.dbpath)["incomplete"], 1
        )
        self.assertEqual(review_ledger.summarize(self.dbpath)["distinct_runs"], 1)

    def test_reimport_same_run_in_different_bundle_does_not_recount(self):
        review_ledger.import_bundle(fixture(), self.dbpath)
        other_bundle = fixture()
        other_bundle["sites"].append({
            "domain": "another.example", "status": "INCOMPLETE",
            "findings": [], "internal_scope_draft": None, "outbound_sent": 0
        })
        counts = review_ledger.import_bundle(other_bundle, self.dbpath)
        self.assertEqual(counts["new_runs"], 0)
        self.assertEqual(counts["updated_findings"], 0)

    def test_invalid_bundle_is_rejected_before_any_database_change(self):
        bad = fixture()
        bad["sites"][0]["outbound_sent"] = 1
        with self.assertRaises(ValueError):
            review_ledger.import_bundle(bad, self.dbpath)
        self.assertFalse(self.dbpath.exists())
        bad = fixture()
        bad["sites"][0]["findings"][0]["observed"] = "x" * 600
        with self.assertRaises(ValueError):
            review_ledger.import_bundle(bad, self.dbpath)
        self.assertFalse(self.dbpath.exists())

    def test_oversize_or_malformed_source_never_imports(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "decoded.json"
            source.write_text("x" * (review_ledger.MAX_SOURCE_BYTES + 1))
            with self.assertRaises(ValueError):
                review_ledger.main([
                    "import", "--input", str(source), "--db", str(self.dbpath),
                ])
            self.assertFalse(self.dbpath.exists())

    def test_public_repository_location_is_blocked(self):
        public_path = Path(review_ledger.__file__).resolve().parents[1] / "secret.sqlite3"
        with self.assertRaisesRegex(ValueError, "outside"):
            review_ledger.import_bundle(fixture(), public_path)

    def test_existing_world_readable_database_is_blocked(self):
        self.dbpath.write_bytes(b"not a database")
        self.dbpath.chmod(0o644)
        with self.assertRaises(ValueError):
            review_ledger.import_bundle(fixture(), self.dbpath)

    def test_cli_prints_counts_only_no_sensitive_site_text(self):
        input_file = self.root / "unsealed.json"
        input_file.write_text(json.dumps(fixture()))
        captured = StringIO()
        with redirect_stdout(captured):
            result = review_ledger.main([
                "import", "--input", str(input_file), "--db", str(self.dbpath),
            ])
        self.assertEqual(result, 0)
        out = captured.getvalue()
        self.assertIn('"new_findings": 1', out)
        self.assertNotIn("example.co.nz", out)
        self.assertNotIn("No title", out)
        self.assertNotIn("INTERNAL SCOPE", out)
        with redirect_stdout(captured):
            self.assertEqual(
                review_ledger.main(["summary", "--db", str(self.dbpath)]), 0
            )


if __name__ == "__main__":
    unittest.main()
