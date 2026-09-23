"""Tests for local SEO report generation."""

from auditor_toolkit.local_seo.report import (
    generate_report,
    LocalSEOReport,
)
from auditor_toolkit.local_seo.identity import LocalBusinessEntity


def test_generate_report_basic():
    entity = LocalBusinessEntity(
        business_id="biz_001",
        canonical_name="ABC Plumbing",
    )
    report = generate_report(
        business_id="biz_001",
        entity=entity,
        findings=[],
        contradictions=[],
    )
    assert isinstance(report, LocalSEOReport)
    assert report.business_id == "biz_001"


def test_report_has_required_fields():
    entity = LocalBusinessEntity(
        business_id="biz_001",
        canonical_name="Test",
    )
    report = generate_report(
        business_id="biz_001",
        entity=entity,
        findings=[],
        contradictions=[],
    )
    assert report.business_id
    assert report.findings is not None
    assert report.provenance is not None
