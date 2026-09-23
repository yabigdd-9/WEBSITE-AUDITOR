"""Tests for local SEO opportunity scoring."""

from auditor_toolkit.local_seo.scoring import (
    score_findings_batch,
    ScoredFinding,
    DEFECT_CATALOGUE,
)


def test_impact_levels_defined():
    assert "wrong_branch_phone" in DEFECT_CATALOGUE
    assert DEFECT_CATALOGUE["wrong_branch_phone"].impact == "HIGH"


def test_score_findings_batch_empty():
    result = score_findings_batch([])
    assert result == []


def test_score_findings_batch_phone_contradiction():
    finding_dict = {
        "defect_key": "wrong_branch_phone",
        "confidence": 0.99,
        "evidence": {},
        "detail": "Phone contradiction detected",
    }
    result = score_findings_batch([finding_dict])
    assert len(result) == 1
    assert result[0].impact == "HIGH"


def test_score_findings_batch_missing_schema():
    finding_dict = {
        "defect_key": "missing_localbusiness_schema",
        "confidence": 0.8,
        "evidence": {},
        "detail": "Missing LocalBusiness schema",
    }
    result = score_findings_batch([finding_dict])
    assert len(result) == 1
    assert result[0].impact == "MEDIUM"


def test_score_findings_batch_format_only_no_flag():
    """Formatting-only differences should not generate high-impact findings."""
    result = score_findings_batch([])
    assert result == []
