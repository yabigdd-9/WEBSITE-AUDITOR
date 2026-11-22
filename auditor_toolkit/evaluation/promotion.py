"""Promotion proposal — human-gated agent promotion.

P1-007 may generate AgentPromotionProposal but may NOT execute:
  activate_model() / deploy_agent() / replace_baseline() / rewrite_policy()
without the existing explicit approval mechanism.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .comparison import ComparisonResult

Action = Literal[
    "PROMOTION_ELIGIBLE",
    "REJECT",
    "MORE_TESTING_REQUIRED",
]

ApprovalStatus = Literal[
    "PENDING",
    "APPROVED",
    "REJECTED",
    "SUPERSEDED",
]


@dataclass
class AgentPromotionProposal:
    """A proposal to promote a candidate agent over the current baseline.

    Deployment still requires human approval through the existing approval
    mechanism (ApprovalStore / AuditLog / existing approval queue).
    """

    proposal_id: str
    candidate_id: str
    baseline_id: str
    eval_run_ids: list[str]
    benchmark_version: str
    baseline_metrics: dict[str, Any]
    candidate_metrics: dict[str, Any]
    deltas: list[dict[str, Any]]
    passed_gates: list[str] = field(default_factory=list)
    failed_gates: list[str] = field(default_factory=list)
    known_regressions: list[str] = field(default_factory=list)
    resource_delta: dict[str, Any] = field(default_factory=dict)
    cost_delta: dict[str, Any] = field(default_factory=dict)
    golden_retention: float = 1.0
    recommended_action: Action = "PROMOTION_ELIGIBLE"
    approval_status: ApprovalStatus = "PENDING"
    approver: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


def create_proposal(
    comparison: ComparisonResult,
    benchmark_version: str = "v36",
    gate_results: dict[str, bool] | None = None,
) -> AgentPromotionProposal:
    """Create a promotion proposal from a comparison result.

    Does NOT deploy — only produces a proposal for human review.
    """
    from datetime import UTC, datetime

    passed = []
    failed = []
    if gate_results:
        for gate, ok in gate_results.items():
            if ok:
                passed.append(gate)
            else:
                failed.append(gate)

    # Determine recommended action
    if comparison.veto_triggered:
        action: Action = "REJECT"
    elif failed:
        action = "MORE_TESTING_REQUIRED"
    else:
        action = "PROMOTION_ELIGIBLE"

    # Extract resource and cost deltas
    c = comparison.candidate_metrics
    b = comparison.baseline_metrics
    _resource_delta = {
        "avg_latency_ms_delta": c.avg_latency_ms - b.avg_latency_ms,
        "avg_cpu_ms_delta": c.avg_cpu_ms - b.avg_cpu_ms,
        "peak_memory_mb_delta": c.peak_memory_mb - b.peak_memory_mb,
    }
    _cost_delta = {
        "estimated_api_cost_delta": c.estimated_api_cost - b.estimated_api_cost,
        "input_token_delta": c.input_token_count - b.input_token_count,
        "output_token_delta": c.output_token_count - b.output_token_count,
    }
    # _resource_delta and _cost_delta reserved for future inclusion in proposal
    del _resource_delta
    del _cost_delta

    return AgentPromotionProposal(
        proposal_id=f"prop-{uuid.uuid4().hex[:12]}",
        candidate_id=comparison.candidate_run_id,
        baseline_id=comparison.baseline_run_id,
        eval_run_ids=[
            comparison.candidate_run_id,
            comparison.baseline_run_id,
        ],
        benchmark_version=benchmark_version,
        baseline_metrics=b.to_dict(),
        candidate_metrics=c.to_dict(),
        deltas=[d.to_dict() for d in comparison.deltas],
        passed_gates=passed,
        failed_gates=failed,
        golden_retention=c.golden_corpus_retention,
        recommended_action=action,
        created_at=datetime.now(UTC).isoformat(),
    )


def approve_proposal(
    proposal: AgentPromotionProposal, approver: str
) -> AgentPromotionProposal:
    """Mark a proposal as approved by a named approver.

    This updates the proposal status but does NOT trigger deployment.
    The existing approval queue / AuditLog handles actual deployment.
    """
    proposal.approval_status = "APPROVED"
    proposal.approver = approver
    return proposal


def reject_proposal(
    proposal: AgentPromotionProposal,
) -> AgentPromotionProposal:
    """Reject a promotion proposal."""
    proposal.approval_status = "REJECTED"
    return proposal


def save_proposal(proposal: AgentPromotionProposal, output_dir, proposal_id: str | None = None) -> str:
    """Persist a proposal to the proposals directory."""
    pid = proposal_id or proposal.proposal_id
    path = output_dir / f"{pid}.json"
    path.write_text(proposal.to_json())
    return str(path)
