"""Local, network-free safety tests for real-site cloud review-only trials."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.cloud_review_only_opportunities import _summary, make_internal_brief, run_review_sites


def sample_report(status="complete", confidence="observed"):
    return {
        "run_id": "local-fixture-001",
        "url": "https://example.com",
        "timestamp": "2026-11-15T00:00:00Z",
        "status": status,
        "checks": {"page": {"status": "ok", "required": True}},
        "evidence": {"page": {"data": {"title": "Example"}}},
        "defects": [{
            "finding_id": "fixture-001",
            "defect_key": "missing_title",
            "defect": "Missing page title",
            "observed": "no title was observed",
            "source_url": "https://example.com",
            "evidence_ref": "page",
            "check": "page",
            "severity": "high",
            "confidence": confidence,
            "remediation_action": "Review a page-specific title",
            "remediation_automation": "AUTO_PREVIEW",
            "effort_band": "XS",
        }],
    }


class TestReviewOnlyScope(unittest.TestCase):
    def test_evidence_backed_draft_is_internal_and_never_priced(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            outcome = make_internal_brief(sample_report(), root)
            self.assertEqual(outcome["evidenced_candidates"], 1)
            self.assertTrue(outcome["internal_scope_draft"])
            self.assertFalse(outcome["outreach_performed"])
            self.assertFalse(outcome["priced"])
            message = (root / "internal-scope-draft.txt").read_text()
            self.assertIn("INTERNAL SCOPE DRAFT - DO NOT SEND", message)
            self.assertIn("Missing page title", message)
            self.assertIn("no title was observed", message)
            self.assertIn("Pricing: NOT SET", message)
            self.assertIn("Human approval required", message)
            self.assertEqual((root / "demo/demo.json").is_file(), True)
            self.assertEqual((root / "remediation/remediation.json").is_file(), True)

    def test_partial_audit_never_generates_a_draft(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(ValueError, "incomplete"):
                make_internal_brief(sample_report(status="partial"), root)
            self.assertFalse((root / "internal-scope-draft.txt").exists())

    def test_heuristic_only_is_not_presented_as_a_verified_opportunity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            outcome = make_internal_brief(sample_report(confidence="heuristic"), root)
            self.assertEqual(outcome["evidenced_candidates"], 0)
            self.assertFalse(outcome["internal_scope_draft"])
            self.assertFalse((root / "internal-scope-draft.txt").exists())

    def test_missing_evidence_check_blocks_candidate(self):
        report = sample_report()
        report["checks"]["page"]["status"] = "error"
        with tempfile.TemporaryDirectory() as temp:
            outcome = make_internal_brief(report, Path(temp))
        self.assertFalse(outcome["internal_scope_draft"])


    def test_unmatched_evidence_reference_cannot_qualify_as_an_opportunity(self):
        report = sample_report()
        report["defects"][0]["evidence_ref"] = "headers"
        with tempfile.TemporaryDirectory() as temp:
            outcome = make_internal_brief(report, Path(temp))
            self.assertEqual(outcome["evidenced_candidates"], 0)
            self.assertFalse(outcome["internal_scope_draft"])

    def test_public_shortlist_reports_sites_and_counts_but_not_website_text(self):
        first = sample_report()
        first["defects"][0]["observed"] = "Sensitive-looking website content not for logs"
        second = sample_report(status="partial")
        sites = [("a.example", "https://a.example"), ("b.example", "https://b.example")]
        with tempfile.TemporaryDirectory() as temp:
            with patch("scripts.cloud_review_only_opportunities.run_audit",
                       side_effect=[first, second]) as audit:
                rows = run_review_sites(sites, Path(temp))
            self.assertEqual(audit.call_count, 2)
        self.assertEqual(rows[0]["evidenced_candidates"], 1)
        self.assertEqual(rows[1]["status"], "INCOMPLETE")
        self.assertFalse(rows[1]["internal_scope_draft"])
        output = _summary(rows)
        self.assertIn("a.example", output)
        self.assertIn("b.example", output)
        self.assertIn("1 | 1 | yes", output)
        self.assertNotIn("Sensitive-looking website content", output)
        self.assertNotIn("no title", output)

    def test_independent_failures_are_generic_and_do_not_block_next_site(self):
        second = sample_report()
        sites = [("a.example", "https://a.example"), ("b.example", "https://b.example")]
        with tempfile.TemporaryDirectory() as temp:
            with patch("scripts.cloud_review_only_opportunities.run_audit",
                       side_effect=[RuntimeError("private server or customer data"), second]):
                rows = run_review_sites(sites, Path(temp))
        self.assertEqual(rows[0]["status"], "ERROR")
        self.assertEqual(rows[1]["status"], "COMPLETE")
        self.assertTrue(rows[1]["internal_scope_draft"])
        self.assertNotIn("private server", _summary(rows))



if __name__ == "__main__":
    unittest.main()
