"""Tests for local SEO report generation."""

from auditor_toolkit.local_seo.identity import build_identity
from auditor_toolkit.local_seo.report import LocalSEOReport, generate_report


def test_generate_report_basic():
    entity = build_identity(
        business_id="biz_001",
        names=[("ABC Plumbing", "homepage")],
    )
    report = generate_report(
        run_id="run_001",
        site_url="https://abc.co.nz/",
        entity=entity.to_dict(),
        findings=[],
        contradictions=[],
    )
    assert isinstance(report, LocalSEOReport)
    assert report.run_id == "run_001"
    assert report.entity["business_id"] == "biz_001"


def test_report_has_required_fields():
    report = generate_report(
        run_id="run_002",
        entity=build_identity(
            business_id="biz_001",
            names=[("Test", "homepage")],
        ).to_dict(),
        findings=[],
        contradictions=[],
    )
    payload = report.to_dict()
    assert payload["run_id"] == "run_002"
    assert payload["findings"] == []
    assert "confidence_metrics" in payload
    assert "metadata" in payload
