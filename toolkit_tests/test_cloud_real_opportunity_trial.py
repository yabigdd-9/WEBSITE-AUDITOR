"""Regressions for the isolated live-evidence review-only cloud trial.

Everything is synthetic here: no network, no customer data, no model calls.
"""
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from scripts.cloud_real_opportunity_trial import (
    _review_candidates, _review_packet, _verified_report, run,
)


class RealEvidenceReviewTrialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.site = "fixture.co.nz"
        self.url = "https://fixture.co.nz"
        self.report = {
            "status": "complete", "url": self.url, "run_id": "synthetic-001",
            "checks": {"page": {"required": True, "status": "ok"}},
            "evidence": {"page": {"observed_at": "synthetic"}},
            "defects": [{
                "finding_id": "f-1", "defect_key": "missing_title",
                "severity": "high", "confidence": "observed",
                "check": "page", "evidence_ref": "page",
                "evidence_summary": "PRIVATE SITE CONTENT NOT FOR LOGGING",
                "remediation_action": "Review page-specific title",
            }],
        }

    def fake_success(self, command, **kwargs):
        path = Path(command[command.index("--output-root") + 1])
        path.mkdir(parents=True, exist_ok=True)
        report = path / "report.json"
        report.write_text(json.dumps(self.report))
        return subprocess.CompletedProcess(
            command, 0,
            json.dumps([{"status": "complete", "artifacts": {"json": str(report)}}]),
            "private response detail",
        )

    def test_review_candidate_has_provenance_and_excludes_heuristics(self):
        self.report["defects"].extend([
            {
                "finding_id": "f-2", "defect_key": "missing_meta_description",
                "severity": "critical", "confidence": "heuristic",
                "evidence_ref": "page", "evidence_summary": "guessed",
            },
            {
                "finding_id": "f-3", "defect_key": "image-alt",
                "severity": "high", "confidence": "observed",
                "evidence_ref": "unavailable", "evidence_summary": "not in source",
            },
            {
                "finding_id": "f-4", "defect_key": "missing_canonical_url",
                "severity": "low", "confidence": "observed",
                "evidence_ref": "page", "evidence_summary": "low priority",
            },
        ])
        result = _review_candidates(self.report)
        self.assertEqual([r["finding_id"] for r in result], ["f-1"])

    def test_run_generates_unsent_draft_without_logging_evidence(self):
        captured = StringIO()
        with redirect_stdout(captured):
            status = run([(self.site, self.url)],
                         output_root=self.root, runner=self.fake_success)
        self.assertEqual(status, 0)
        output = captured.getvalue()
        self.assertIn("fixture.co.nz", output)
        self.assertIn("| PASS | 1 | 1 |", output)
        self.assertNotIn("PRIVATE SITE CONTENT", output)
        packet = json.loads((
            self.root / self.site / "review/private-review-draft.json"
        ).read_text())
        draft = packet["draft_proposal"]
        self.assertEqual(len(draft["observations"]), 1)
        self.assertEqual(draft["price_nzd"], None)
        self.assertFalse(draft["send_approved"])
        self.assertFalse(draft["customer_approved"])
        self.assertEqual(draft["external_sends"], 0)
        self.assertEqual(draft["model_calls"], 0)
        self.assertEqual(draft["cost_nzd"], 0)
        self.assertTrue((
            self.root / self.site / "review/preview-only/remediation.json"
        ).is_file())

    def test_commands_remain_bounded_and_no_paid_or_browser(self):
        commands = []
        def fake_runner(command, **kwargs):
            commands.append((command, kwargs))
            return self.fake_success(command, **kwargs)
        with redirect_stdout(StringIO()):
            self.assertEqual(run(
                [("www.jcconstruction.co.nz", "https://www.jcconstruction.co.nz")],
                output_root=self.root, runner=fake_runner,
            ), 1)  # mismatched fixture audit URL must fail closed
        command, options = commands[0]
        self.assertEqual(command[command.index("--max-bytes") + 1], "5000000")
        self.assertEqual(command[command.index("--max-pages") + 1], "2")
        self.assertEqual(command[command.index("--max-depth") + 1], "1")
        self.assertEqual(command[command.index("--concurrency") + 1], "1")
        self.assertEqual(options["timeout"], 150)
        self.assertNotIn("--ai", command)
        self.assertNotIn("--browser", command)

    def test_reports_cannot_escape_temporary_dir(self):
        with tempfile.TemporaryDirectory() as another:
            report_path = Path(another) / "report.json"
            report_path.write_text(json.dumps(self.report))
            record = json.dumps([
                {"status": "complete", "artifacts": {"json": str(report_path)}}
            ])
            with self.assertRaises(ValueError):
                _verified_report(record, self.root, self.url)

    def test_no_findings_means_no_proposal_draft(self):
        self.report["defects"] = []
        captured = StringIO()
        with redirect_stdout(captured):
            self.assertEqual(run(
                [(self.site, self.url)], output_root=self.root,
                runner=self.fake_success,
            ), 0)
        self.assertIn("| PASS | 0 | 0 |", captured.getvalue())
        self.assertFalse((
            self.root / self.site / "review/private-review-draft.json"
        ).exists())

    def test_failed_required_check_does_not_make_a_draft(self):
        self.report["checks"]["page"]["status"] = "error"
        with redirect_stdout(StringIO()):
            self.assertEqual(run(
                [(self.site, self.url)], output_root=self.root,
                runner=self.fake_success,
            ), 1)
        self.assertFalse((
            self.root / self.site / "review/private-review-draft.json"
        ).exists())

    def test_subprocess_failure_leaks_no_untrusted_evidence(self):
        def fake_runner(command, **kwargs):
            return subprocess.CompletedProcess(
                command, 2, "SECRET_SITE_HTML", "SECRET_ERROR",
            )
        captured = StringIO()
        with redirect_stdout(captured):
            self.assertEqual(run(
                [(self.site, self.url)], output_root=self.root,
                runner=fake_runner,
            ), 1)
        self.assertIn("| FAIL | 0 | 0 |", captured.getvalue())
        self.assertNotIn("SECRET", captured.getvalue())

    def test_invalid_report_blocks_unverified_draft(self):
        self.report["status"] = "partial"
        with redirect_stdout(StringIO()):
            self.assertEqual(run(
                [(self.site, self.url)], output_root=self.root,
                runner=self.fake_success,
            ), 1)

    def test_timeout_fails_closed(self):
        def fake_runner(command, **kwargs):
            raise subprocess.TimeoutExpired(command, kwargs["timeout"],
                                            output=b"PRIVATE")
        with redirect_stdout(StringIO()):
            self.assertEqual(run(
                [(self.site, self.url)], output_root=self.root,
                runner=fake_runner,
            ), 1)


if __name__ == "__main__":
    unittest.main()
