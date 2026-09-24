import pytest
import os
import json
from proposal_engine.schema import Proposal
from proposal_engine.closeout import (
    record_proposal_quality_metrics,
    confirm_autonomous_sends,
    confirm_binding_quotes,
    produce_closeout,
    run_closeout
)


def test_20_proposal_pilot():
    proposals = [
        {
            "proposal_id": f"P{i}",
            "business_id": "B",
            "website_id": "W",
            "opportunity_id": "O",
            "proof_id": "F",
            "deliverables": ["Audit Report", "Fix List"],
            "acceptance_criteria": ["All critical issues resolved"],
            "assumptions": ["Client provides access"],
            "limitations": ["No server access"],
            "optional_addons": ["Monthly monitoring"],
            "evidence_refs": ["E1", "E2"],
            "exclusions": ["hosting", "domain_registration", "third_party_apis", "content_creation", "legal_review"],
            "claims": [{"claim": "Fixes critical issues", "evidence_ref": "E1"}],
            "status": "HUMAN_APPROVED",
            "external_send": False,
            "binding_quote": False,
            "quote": {"high_estimate": 5000},
            "inputs": {"hours": 50},
            "scope_items": [
                {"scope_id": "S1", "effort_band": "M"},
                {"scope_id": "S2", "effort_band": "L"}
            ]
        }
        for i in range(20)
    ]

    actual_outcomes = [
        {
            "actual_items": [
                {"scope_id": "S1", "effort_band": "M"},
                {"scope_id": "S2", "effort_band": "L"}
            ],
            "actual_cost": 4800
        }
        for i in range(20)
    ]

    result = run_closeout(proposals, actual_outcomes)

    assert os.path.exists(result["metrics_file"])
    assert os.path.exists(result["closeout_file"])
    assert result["autonomous_sends_ok"] is True
    assert result["binding_quotes_ok"] is True

    # Verify metrics content
    with open(result["metrics_file"]) as f:
        metrics = json.load(f)

    assert metrics["total_proposals"] == 20
    assert metrics["scope_correctness"] == 1.0
    assert metrics["pricing_reproducibility"] == 1.0
    assert metrics["missing_exclusions"] <= 0.1
    assert metrics["proposal_clarity"] >= 0.8
    assert metrics["estimate_accuracy"] >= 0.85
    assert metrics["compliance_score"] == 1.0

    # Verify closeout report exists and has content
    with open(result["closeout_file"]) as f:
        report = f.read()

    assert "Phase Closeout Report" in report
    assert "Scope Correctness" in report
    assert "✓ PASS" in report


if __name__ == "__main__":
    test_20_proposal_pilot()
    print("20-proposal pilot test passed")