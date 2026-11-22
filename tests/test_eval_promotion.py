"""Tests for evaluation promotion proposals."""

import json

from auditor_toolkit.evaluation.comparison import compare
from auditor_toolkit.evaluation.promotion import (
    approve_proposal,
    create_proposal,
    reject_proposal,
    save_proposal,
)
from auditor_toolkit.evaluation.schema import EvalMetrics


def _make_metrics(run_id="run", **overrides):
    defaults = {
        "run_id": run_id,
        "total_cases": 10,
        "pass_count": 7,
        "fail_count": 3,
        "finding_precision": 0.80,
        "finding_recall": 0.70,
        "high_confidence_fp_rate": 0.03,
        "unsupported_claim_rate": 0.08,
        "correct_abstention_rate": 0.85,
        "incorrect_abstention_rate": 0.15,
        "evidence_precision": 0.75,
        "evidence_recall": 0.70,
        "golden_corpus_retention": 1.0,
        "wrong_business_rate": 0.01,
        "prohibited_action_count": 0,
        "tool_policy_violation_count": 0,
        "completion_rate": 0.70,
        "browser_failure_rate": 0.0,
        "agent_failure_rate": 0.05,
        "avg_latency_ms": 1000.0,
        "avg_cpu_ms": 600.0,
        "peak_memory_mb": 128.0,
        "input_token_count": 4000,
        "output_token_count": 2500,
        "estimated_api_cost": 0.0,
    }
    defaults.update(overrides)
    return EvalMetrics(**defaults)


def test_create_proposal_eligible():
    baseline = _make_metrics(run_id="baseline")
    candidate = _make_metrics(
        run_id="candidate",
        finding_precision=0.90,
        avg_latency_ms=800.0,
    )
    comparison = compare(candidate, baseline)

    gates = {
        "gate_01_no_irreversible_actions": True,
        "gate_04_golden_false_positive_retention": True,
    }

    proposal = create_proposal(comparison, gate_results=gates)
    assert proposal.recommended_action == "PROMOTION_ELIGIBLE"
    assert proposal.approval_status == "PENDING"
    assert proposal.golden_retention == 1.0


def test_create_proposal_rejected_by_veto():
    baseline = _make_metrics(
        run_id="baseline",
        high_confidence_fp_rate=0.02,
    )
    candidate = _make_metrics(
        run_id="candidate",
        high_confidence_fp_rate=0.10,
    )
    comparison = compare(candidate, baseline)

    proposal = create_proposal(comparison)
    assert proposal.recommended_action == "REJECT"


def test_create_proposal_more_testing():
    baseline = _make_metrics(run_id="baseline")
    candidate = _make_metrics(run_id="candidate", finding_precision=0.82)
    comparison = compare(candidate, baseline)

    gates = {
        "gate_pass": True,
        "gate_fail": False,
    }

    proposal = create_proposal(comparison, gate_results=gates)
    assert proposal.recommended_action == "MORE_TESTING_REQUIRED"
    assert "gate_fail" in proposal.failed_gates


def test_approve_proposal():
    baseline = _make_metrics(run_id="baseline")
    candidate = _make_metrics(run_id="candidate")
    comparison = compare(candidate, baseline)
    proposal = create_proposal(comparison)

    approved = approve_proposal(proposal, "admin@example.com")
    assert approved.approval_status == "APPROVED"
    assert approved.approver == "admin@example.com"


def test_reject_proposal():
    baseline = _make_metrics(run_id="baseline")
    candidate = _make_metrics(run_id="candidate", prohibited_action_count=1)
    comparison = compare(candidate, baseline)
    proposal = create_proposal(comparison)

    rejected = reject_proposal(proposal)
    assert rejected.approval_status == "REJECTED"


def test_proposal_to_dict():
    baseline = _make_metrics(run_id="baseline")
    candidate = _make_metrics(run_id="candidate")
    comparison = compare(candidate, baseline)
    proposal = create_proposal(comparison)

    d = proposal.to_dict()
    assert "proposal_id" in d
    assert "candidate_metrics" in d
    assert "baseline_metrics" in d
    assert "deltas" in d


def test_proposal_to_json():
    baseline = _make_metrics(run_id="baseline")
    candidate = _make_metrics(run_id="candidate")
    comparison = compare(candidate, baseline)
    proposal = create_proposal(comparison)

    j = proposal.to_json()
    data = json.loads(j)
    assert data["proposal_id"] == proposal.proposal_id


def test_save_proposal(tmp_path):
    baseline = _make_metrics(run_id="baseline")
    candidate = _make_metrics(run_id="candidate")
    comparison = compare(candidate, baseline)
    proposal = create_proposal(comparison)

    path = save_proposal(proposal, tmp_path, "test_prop")
    assert path.endswith("test_prop.json")
    assert tmp_path.joinpath("test_prop.json").exists()


def test_proposal_does_not_deploy():
    """Verify that creating and approving a proposal does not trigger deployment."""
    baseline = _make_metrics(run_id="baseline")
    candidate = _make_metrics(run_id="candidate")
    comparison = compare(candidate, baseline)
    proposal = create_proposal(comparison)
    approve_proposal(proposal, "admin")

    # Proposal should remain in PENDING/APPROVED status, not DEPLOYED
    assert proposal.approval_status == "APPROVED"
    assert proposal.recommended_action != "DEPLOY"
