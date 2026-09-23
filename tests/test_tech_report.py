"""Tests for technology enrichment report generation."""

import tempfile
from pathlib import Path

from auditor_toolkit.technology.report import generate_report, save_report
from auditor_toolkit.technology.schema import TechEnrichmentResult, TechFingerprint, VersionInfo, VulnerabilityAdvisory


def _make_result(**kw):
    defaults = {
        "url": "https://example.com",
        "fingerprint": TechFingerprint(),
        "run_id": "test-001",
    }
    defaults.update(kw)
    return TechEnrichmentResult(**defaults)


def test_generate_report_basic():
    result = _make_result()
    md = generate_report(result)
    assert "Technology Report" in md
    assert "https://example.com" in md


def test_generate_report_with_versions():
    result = _make_result(
        versions=[VersionInfo(name="WordPress", detected_version="5.8", is_outdated=True)],
    )
    md = generate_report(result)
    assert "WordPress" in md
    assert "5.8" in md


def test_generate_report_with_vulns():
    result = _make_result(
        vulnerabilities=[VulnerabilityAdvisory(component="WordPress", severity="high", cve_id="CVE-2023-1234")],
    )
    md = generate_report(result)
    assert "CVE-2023-1234" in md


def test_save_report(tmp_path):
    result = _make_result()
    json_path, md_path = save_report(result, tmp_path)
    assert json_path.exists()
    assert md_path.exists()
