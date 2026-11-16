"""Meaningful, local-only coverage for technology evidence and report outputs."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from auditor_toolkit.technology.report import (
    _severity_icon,
    _severity_rank,
    generate_json_report,
    generate_report,
    generate_stack_summary_markdown,
    save_report,
)
from auditor_toolkit.technology.schema import (
    TechDetection,
    TechEnrichmentResult,
    TechFingerprint,
    VersionInfo,
    VulnerabilityAdvisory,
)


def detection(name, category, confidence=0.9):
    return TechDetection(name=name, category=category, confidence=confidence)


def sample_result():
    return TechEnrichmentResult(
        url="https://example.co.nz",
        fingerprint=TechFingerprint(
            cms=detection("WordPress", "cms", 0.9),
            framework=detection("React", "framework", 0.8),
            language=detection("PHP", "language", 0.7),
            server=detection("nginx", "server"),
            cdn=detection("Cloud CDN", "cdn"),
            ecommerce=detection("Shop", "ecommerce"),
            hosting=detection("Local Host", "hosting"),
            analytics=[detection("Analytics A", "analytics")],
            payment=[detection("Payments B", "payment")],
        ),
        versions=[
            VersionInfo(name="WordPress", detected_version="6.1", latest_version="6.5",
                        is_outdated=True),
            VersionInfo(name="nginx", detected_version="1.2", latest_version="1.2",
                        is_outdated=False),
        ],
        vulnerabilities=[
            VulnerabilityAdvisory(
                component="WordPress",
                version="6.1",
                severity="high",
                cve_id="CVE-2026-0001",
                description="Synthetic advisory for offline test",
                remediation="Update after site-owner approval",
            ),
            VulnerabilityAdvisory(
                component="nginx",
                version="1.2",
                severity="medium",
                description="Second synthetic advisory",
                remediation="Review configuration",
            ),
        ],
        run_id="test-run-001",
        completed_at="2026-11-16T00:00:00+00:00",
        duration_seconds=1.7,
        errors=["Synthetic parser warning"],
    )


class TestTechnologyReports(unittest.TestCase):
    def test_empty_report_does_not_invent_technology_or_vulnerabilities(self):
        result = TechEnrichmentResult(
            url="https://example.co.nz", fingerprint=TechFingerprint(), run_id="empty"
        )
        markdown = generate_report(result)
        self.assertIn("No version information detected.", markdown)
        self.assertIn("No known vulnerabilities detected.", markdown)
        self.assertNotIn("## Errors", markdown)
        summary = json.loads(generate_json_report(result))["summary"]
        self.assertEqual(summary["total_technologies_detected"], 0)
        self.assertEqual(summary["outdated_components"], 0)
        self.assertEqual(summary["total_vulnerabilities"], 0)
        self.assertEqual(summary["severity_breakdown"], {})

    def test_report_contains_observed_stack_versions_advisories_and_errors(self):
        result = sample_result()
        report = generate_report(result)
        self.assertIn("Technology Report — https://example.co.nz", report)
        self.assertIn("CMS:** WordPress (90%)", report)
        self.assertIn("Framework:** React (80%)", report)
        self.assertIn("Language:** PHP (70%)", report)
        self.assertIn("Server:** nginx", report)
        self.assertIn("CDN:** Cloud CDN", report)
        self.assertIn("E-commerce:** Shop", report)
        self.assertIn("Analytics:** Analytics A", report)
        self.assertIn("Payment:** Payments B", report)
        self.assertIn("⚠️ OUTDATED", report)
        self.assertIn("✅ Current", report)
        self.assertIn("CVE-2026-0001", report)
        self.assertIn("Update after site-owner approval", report)
        self.assertIn("## Errors", report)
        self.assertIn("Synthetic parser warning", report)

    def test_summary_counts_match_input_not_derived_commercial_claims(self):
        payload = json.loads(generate_json_report(sample_result()))
        self.assertEqual(payload["report_type"], "technology_enrichment")
        self.assertEqual(payload["report_version"], "1.0")
        self.assertEqual(payload["summary"]["total_technologies_detected"], 9)
        self.assertEqual(payload["summary"]["total_versions_detected"], 2)
        self.assertEqual(payload["summary"]["outdated_components"], 1)
        self.assertEqual(payload["summary"]["total_vulnerabilities"], 2)
        self.assertEqual(payload["summary"]["severity_breakdown"], {
            "high": 1, "medium": 1,
        })
        self.assertIn("generated_at", payload)
        self.assertNotIn("revenue", payload["summary"])

    def test_saved_json_and_markdown_match_direct_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "private"
            result = sample_result()
            json_path, markdown_path = save_report(result, output, run_id="manual-001")
            self.assertEqual(json_path.name, "manual-001.json")
            self.assertEqual(markdown_path.name, "manual-001.md")
            self.assertEqual(json.loads(json_path.read_text()), result.to_dict())
            self.assertEqual(markdown_path.read_text(), generate_report(result))
            self.assertEqual(save_report(result, output)[0].name, "test-run-001.json")

    def test_stack_markdown_distinguishes_absent_evidence_and_cve(self):
        text = generate_stack_summary_markdown(sample_result().tech_stack)
        self.assertIn("Hosting:** Local Host", text)
        self.assertIn("WordPress:** 6.1 (⚠️ outdated)", text)
        self.assertIn("nginx:** 1.2 (✅ current)", text)
        self.assertIn("🟠 **WordPress (CVE-2026-0001)", text)
        self.assertIn("🟡 **nginx:", text)
        empty = generate_stack_summary_markdown(
            TechEnrichmentResult(url="https://example.co.nz",
                                 fingerprint=TechFingerprint()).tech_stack
        )
        self.assertIn("CMS:** Not detected", empty)
        self.assertIn("Hosting:** Not detected", empty)
        self.assertNotIn("## Vulnerabilities", empty)

    def test_severity_helpers_handle_known_and_unknown_values(self):
        self.assertEqual(_severity_icon("critical"), "🔴")
        self.assertEqual(_severity_icon("high"), "🟠")
        self.assertEqual(_severity_icon("medium"), "🟡")
        self.assertEqual(_severity_icon("low"), "🟢")
        self.assertEqual(_severity_icon("unknown"), "⚪")
        self.assertGreater(_severity_rank("critical"), _severity_rank("high"))
        self.assertGreater(_severity_rank("high"), _severity_rank("medium"))
        self.assertEqual(_severity_rank("unknown"), 0)


if __name__ == "__main__":
    unittest.main()
