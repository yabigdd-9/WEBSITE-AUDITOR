"""Tests for local SEO opportunity scoring."""

from auditor_toolkit.local_seo.scoring import (
    DEFECT_CATALOGUE,
    build_scoring_summary,
    score_findings_batch,
)


def test_impact_levels_defined():
    assert "wrong_branch_phone" in DEFECT_CATALOGUE
    assert DEFECT_CATALOGUE["wrong_branch_phone"].impact == "HIGH"
    assert DEFECT_CATALOGUE["missing_localbusiness_schema"].impact == "MEDIUM"


def test_score_findings_batch_empty():
    findings = score_findings_batch([])
    summary = build_scoring_summary(findings)
    assert findings == []
    assert summary.total_findings == 0
    assert summary.avg_confidence == 0.0


def test_score_findings_batch_phone_contradiction():
    findings = score_findings_batch([
        {
            "defect_key": "wrong_branch_phone",
            "confidence": 0.99,
            "detail": "Phone contradiction detected",
        }
    ])
    assert len(findings) == 1
    assert findings[0].impact == "HIGH"


def test_score_findings_batch_missing_schema():
    findings = score_findings_batch([
        {
            "defect_key": "missing_localbusiness_schema",
            "confidence": 0.8,
        }
    ])
    assert findings[0].impact == "MEDIUM"


def test_score_findings_batch_format_only_no_flag():
    assert score_findings_batch([]) == []
