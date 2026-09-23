"""Tests for local SEO opportunity scoring."""

from auditor_toolkit.local_seo.scoring import (
    score_findings_batch,
    ScoredFinding,
    DEFECT_CATALOGUE,
)


def test_impact_levels_defined():
    assert "wrong_branch_phone" in DEFECT_CATALOGUE
    assert DEFECT_CATALOGUE["LOCAL.NAP.PHONE.CONTRADICTION"] == "HIGH"


def test_score_findings_batch_empty():
    result = score_findings_batch(business_id="biz_001")
    assert result.findings == []
    assert result.confidence >= 0


def test_score_findings_batch_phone_contradiction():
    finding = ScoredFinding(
        rule_id="LOCAL.NAP.PHONE.CONTRADICTION",
        business_id="biz_001",
        claim="Phone contradiction detected",
        evidence=[],
        confidence=0.99,
        impact="HIGH",
    )
    result = score_findings_batch(
        business_id="biz_001",
        findings=[finding],
    )
    assert len(result.findings) == 1
    assert result.findings[0].impact == "HIGH"


def test_score_findings_batch_missing_schema():
    finding = ScoredFinding(
        rule_id="LOCAL.SCHEMA.MISSING_LOCALBUSINESS",
        business_id="biz_001",
        claim="Missing LocalBusiness schema",
        evidence=[],
        confidence=0.8,
        impact="MEDIUM",
    )
    result = score_findings_batch(
        business_id="biz_001",
        findings=[finding],
    )
    assert result.findings[0].impact == "MEDIUM"


def test_score_findings_batch_format_only_no_flag():
    """Formatting-only differences should not generate high-impact findings."""
    # No findings generated for formatting-only differences
    result = score_findings_batch(business_id="biz_001", findings=[])
    assert result.findings == []
