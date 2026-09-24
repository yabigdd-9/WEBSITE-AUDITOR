import json
import sys

import pytest

from proposal_quote_intelligence.analytics.dashboard import ProposalAnalyticsDashboard
from proposal_quote_intelligence.approval.workflow import ApprovalWorkflow
from proposal_quote_intelligence.cli import main
from proposal_quote_intelligence.monitoring.health_check import check_configuration
from proposal_quote_intelligence.schema import ProposalSchema
from proposal_quote_intelligence.scoring.model import ProofScorer


def test_score_is_bounded_and_weights_are_normalized():
    scorer = ProofScorer({"confidence": 2, "effort_savings": 1, "business_impact": 1})

    score = scorer.score_proof(
        {"confidence": "HIGH", "effort_saved_hours": 20, "business_impact_score": 150}
    )

    assert score == 100
    assert sum(scorer.weights.values()) == pytest.approx(1)


@pytest.mark.parametrize("weights", [{"confidence": -1}, {"confidence": 0, "effort_savings": 0, "business_impact": 0}])
def test_invalid_score_weights_are_rejected(weights):
    with pytest.raises(ValueError):
        ProofScorer(weights)


def test_new_version_does_not_share_nested_mutable_values():
    proposal = ProposalSchema(
        "p1", "b1", "https://example.com", findings=[{"evidence": ["old"]}], pricing={"total": 1}
    )

    next_version = proposal.new_version()
    next_version.findings[0]["evidence"].append("new")
    next_version.pricing["total"] = 2

    assert proposal.findings == [{"evidence": ["old"]}]
    assert proposal.pricing == {"total": 1}


def test_approval_hash_detects_content_change():
    proposal = ProposalSchema("p1", "b1", "https://example.com")
    proposal.approve()
    approved_hash = proposal.approval_hash

    proposal.scope.append("changed after approval")

    assert proposal.compute_hash() != approved_hash
    assert not proposal.is_approval_valid()
    with pytest.raises(ValueError, match="create a new version"):
        proposal.approve()


def test_workflow_does_not_expose_mutable_transition_table():
    workflow = ApprovalWorkflow()
    transitions = workflow.get_allowed_transitions()
    transitions.clear()

    assert workflow.can_transition("REVIEWED")


def test_conversion_rate_excludes_drafts():
    dashboard = ProposalAnalyticsDashboard()
    dashboard.add_proposal({"status": "DRAFT"})
    dashboard.add_proposal({"status": "ACCEPTED"})
    dashboard.add_proposal({"status": "REJECTED"})

    assert dashboard.get_conversion_rate() == 50


def test_cli_approve_updates_proposal_file(monkeypatch, tmp_path, capsys):
    path = tmp_path / "proposal.json"
    path.write_text(
        json.dumps(ProposalSchema("p1", "b1", "https://example.com").to_dict()), encoding="utf-8"
    )
    monkeypatch.setattr(sys, "argv", ["wa-proposal", "approve", "--proposal-file", str(path)])

    assert main() == 0
    approved = ProposalSchema.from_dict(json.loads(path.read_text(encoding="utf-8")))
    assert approved.status == "APPROVED"
    assert approved.is_immutable
    assert approved.approval_hash == approved.compute_hash()
    assert "Approved proposal p1" in capsys.readouterr().out


def test_health_check_validates_required_configs():
    check_configuration()
