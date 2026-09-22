from auditor_toolkit.faults import enrich, group_root_causes, regression
from auditor_toolkit.proofing import build_claim_ledger, proof_draft


def test_faults_group_correlated_browser_symptoms():
    defects = [
        {"finding_id": "a", "defect_key": "javascript_error", "check": "browser", "observed": "TypeError"},
        {"finding_id": "b", "defect_key": "failed_request", "check": "browser", "observed": "/api/quote 500"},
    ]
    enriched = [enrich(item) for item in defects]
    groups = group_root_causes(enriched)
    assert groups[0]["root_cause_id"] == "client_runtime_failure"
    assert groups[0]["likely"] is True
    assert groups[0]["confidence"] == "MODERATE"


def test_fault_regression_is_stable():
    current = [{"finding_id": "new"}, {"finding_id": "same"}]
    previous = [{"finding_id": "old"}, {"finding_id": "same"}]
    assert regression(current, previous) == {"new": ["new"], "resolved": ["old"], "unchanged": ["same"]}


def test_claim_ledger_rejects_unbounded_draft_claims():
    report = {
        "url": "https://fixture.example",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "defects": [{
            "finding_id": "f1", "defect": "Missing title", "confidence_assessment": {"class": "PROVEN"},
            "evidence_ref": "page", "evidence_summary": "no title element", "source_url": "https://fixture.example",
        }],
    }
    claims = build_claim_ledger(report)
    result = proof_draft("Your site is guaranteed to double revenue.", claims)
    assert result["passed"] is False
    assert result["human_review_required"] is True
    assert claims[0]["claim_type"] == "observed_fact"


def test_heuristic_label_stays_weak_despite_evidence():
    """An explicit heuristic label must never masquerade as observed fact."""
    defect = {
        "finding_id": "h1", "defect_key": "ux", "check": "ux",
        "confidence": "heuristic", "evidence_summary": "no form detected",
    }
    enriched = enrich(defect)
    assert enriched["confidence_assessment"]["class"] == "WEAK"
    claims = build_claim_ledger({
        "url": "https://fixture.example", "timestamp": "2026-01-01T00:00:00+00:00",
        "defects": [defect],
    })
    assert claims[0]["claim_type"] == "hypothesis"


def test_proof_draft_rejects_100_percent_claims():
    assert proof_draft("We deliver 100% guaranteed results.", [])["passed"] is False
    assert proof_draft("Around 100 % of work is local.", [])["passed"] is False
    assert proof_draft("We reduced load time below 100 ms.", [])["passed"] is True
