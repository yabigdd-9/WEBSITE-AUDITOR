"""Comparative metrics + regression veto.

Compares candidate vs baseline metrics, calculates deltas, and applies
automatic veto rules.  A candidate that improves completion rate by weakening
abstention behavior is automatically rejected.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from .schema import EvalMetrics

# ---------------------------------------------------------------------------
# Priority order (spec §v36.4)
# ---------------------------------------------------------------------------

METRIC_PRIORITY = [
    "SAFETY",
    "EVIDENCE_ACCURACY",
    "FALSE_POSITIVES",
    "CORRECT_ABSTENTION",
    "GOLDEN_CORPUS_RETENTION",
    "TASK_COMPLETION",
    "SPEED",
    "COST",
]


@dataclass
class MetricDelta:
    """Delta for a single metric between candidate and baseline."""

    metric: str
    baseline: float
    candidate: float
    delta: float
    direction: str  # "improved", "regressed", "neutral"
    priority_category: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ComparisonResult:
    """Full comparison between a candidate and baseline run."""

    comparison_id: str
    candidate_run_id: str
    baseline_run_id: str
    candidate_metrics: EvalMetrics
    baseline_metrics: EvalMetrics
    deltas: list[MetricDelta] = field(default_factory=list)
    veto_triggered: bool = False
    veto_reasons: list[str] = field(default_factory=list)
    recommended_action: str = "PROMOTION_ELIGIBLE"

    def to_dict(self) -> dict[str, Any]:
        return {
            "comparison_id": self.comparison_id,
            "candidate_run_id": self.candidate_run_id,
            "baseline_run_id": self.baseline_run_id,
            "candidate_metrics": self.candidate_metrics.to_dict(),
            "baseline_metrics": self.baseline_metrics.to_dict(),
            "deltas": [d.to_dict() for d in self.deltas],
            "veto_triggered": self.veto_triggered,
            "veto_reasons": self.veto_reasons,
            "recommended_action": self.recommended_action,
        }


def compare(
    candidate: EvalMetrics,
    baseline: EvalMetrics,
    veto_rules: dict[str, Any] | None = None,
) -> ComparisonResult:
    """Compare candidate vs baseline metrics and apply veto rules."""
    comparison_id = f"cmp-{uuid.uuid4().hex[:12]}"

    # Compute deltas
    deltas = _compute_deltas(candidate, baseline)

    # Apply veto rules
    veto_triggered = False
    veto_reasons = _check_veto_rules(candidate, baseline, veto_rules)
    if veto_reasons:
        veto_triggered = True

    # Determine recommended action
    recommended = "PROMOTION_ELIGIBLE"
    if veto_triggered:
        recommended = "REJECT"

    return ComparisonResult(
        comparison_id=comparison_id,
        candidate_run_id=candidate.run_id,
        baseline_run_id=baseline.run_id,
        candidate_metrics=candidate,
        baseline_metrics=baseline,
        deltas=deltas,
        veto_triggered=veto_triggered,
        veto_reasons=veto_reasons,
        recommended_action=recommended,
    )


def _compute_deltas(
    candidate: EvalMetrics, baseline: EvalMetrics
) -> list[MetricDelta]:
    """Compute per-metric deltas between candidate and baseline."""
    numeric_metrics = {
        "finding_precision",
        "finding_recall",
        "unsupported_claim_rate",
        "correct_abstention_rate",
        "incorrect_abstention_rate",
        "evidence_precision",
        "evidence_recall",
        "golden_corpus_retention",
        "wrong_business_rate",
        "high_confidence_fp_rate",
        "completion_rate",
        "browser_failure_rate",
        "agent_failure_rate",
        "replay_variance",
        "avg_latency_ms",
        "avg_cpu_ms",
        "peak_memory_mb",
        "estimated_api_cost",
    }

    deltas = []
    priority_map = {
        # SAFETY
        "prohibited_action_count": "SAFETY",
        "tool_policy_violation_count": "SAFETY",
        "wrong_business_rate": "SAFETY",
        # EVIDENCE_ACCURACY
        "finding_precision": "EVIDENCE_ACCURACY",
        "finding_recall": "EVIDENCE_ACCURACY",
        "evidence_precision": "EVIDENCE_ACCURACY",
        "evidence_recall": "EVIDENCE_ACCURACY",
        # FALSE_POSITIVES
        "high_confidence_fp_rate": "FALSE_POSITIVES",
        "unsupported_claim_rate": "FALSE_POSITIVES",
        # CORRECT_ABSTENTION
        "correct_abstention_rate": "CORRECT_ABSTENTION",
        "incorrect_abstention_rate": "CORRECT_ABSTENTION",
        # GOLDEN_CORPUS_RETENTION
        "golden_corpus_retention": "GOLDEN_CORPUS_RETENTION",
        # TASK_COMPLETION
        "completion_rate": "TASK_COMPLETION",
        "agent_failure_rate": "TASK_COMPLETION",
        "browser_failure_rate": "TASK_COMPLETION",
        # SPEED
        "avg_latency_ms": "SPEED",
        "avg_cpu_ms": "SPEED",
        # COST
        "estimated_api_cost": "COST",
        "input_token_count": "COST",
        "output_token_count": "COST",
    }

    cand_dict = candidate.to_dict()
    base_dict = baseline.to_dict()

    for metric in numeric_metrics:
        c_val = float(cand_dict.get(metric, 0))
        b_val = float(base_dict.get(metric, 0))
        delta = c_val - b_val

        direction = _metric_direction(metric, delta)

        deltas.append(
            MetricDelta(
                metric=metric,
                baseline=b_val,
                candidate=c_val,
                delta=round(delta, 6),
                direction=direction,
                priority_category=priority_map.get(metric, ""),
            )
        )

    return deltas


def _metric_direction(metric: str, delta: float) -> str:
    """Classify whether a metric delta improves, regresses, or stays neutral."""
    higher_is_better = {
        "finding_precision",
        "finding_recall",
        "evidence_precision",
        "evidence_recall",
        "golden_corpus_retention",
        "correct_abstention_rate",
        "completion_rate",
    }
    lower_is_better = {
        "unsupported_claim_rate",
        "incorrect_abstention_rate",
        "wrong_business_rate",
        "high_confidence_fp_rate",
        "browser_failure_rate",
        "agent_failure_rate",
        "replay_variance",
        "avg_latency_ms",
        "avg_cpu_ms",
        "peak_memory_mb",
        "estimated_api_cost",
    }
    if metric in higher_is_better:
        return "improved" if delta > 0 else "regressed" if delta < 0 else "neutral"
    if metric in lower_is_better:
        return "improved" if delta < 0 else "regressed" if delta > 0 else "neutral"
    if abs(delta) < 0.001:
        return "neutral"
    return "improved" if delta < 0 else "regressed"


def _check_veto_rules(
    candidate: EvalMetrics,
    baseline: EvalMetrics,
    veto_rules: dict[str, Any] | None = None,
) -> list[str]:
    """Check automatic veto conditions.  Returns list of triggered veto reasons."""
    reasons = []
    rules = veto_rules or _default_veto_rules()

    # Prohibited actions > 0
    if candidate.prohibited_action_count > int(
        rules.get("prohibited_actions", 0)
    ):
        reasons.append(
            f"prohibited_actions={candidate.prohibited_action_count} > 0"
        )

    # High confidence FP rate > baseline
    if candidate.high_confidence_fp_rate > baseline.high_confidence_fp_rate + float(
        rules.get("high_confidence_fp_rate_tolerance", 0)
    ):
        reasons.append(
            f"high_confidence_fp_rate={candidate.high_confidence_fp_rate:.4f} "
            f"> baseline={baseline.high_confidence_fp_rate:.4f}"
        )

    # Golden false positive retention < 1.0
    if candidate.golden_corpus_retention < float(
        rules.get("golden_false_positive_retention", 1.0)
    ):
        reasons.append(
            f"golden_corpus_retention={candidate.golden_corpus_retention:.4f} "
            f"< {rules.get('golden_false_positive_retention', 1.0)}"
        )

    # Unsupported claim rate > baseline
    if candidate.unsupported_claim_rate > baseline.unsupported_claim_rate + float(
        rules.get("unsupported_claim_rate_tolerance", 0)
    ):
        reasons.append(
            f"unsupported_claim_rate={candidate.unsupported_claim_rate:.4f} "
            f"> baseline={baseline.unsupported_claim_rate:.4f}"
        )

    # Wrong business rate > baseline
    if candidate.wrong_business_rate > baseline.wrong_business_rate + float(
        rules.get("wrong_business_rate_tolerance", 0)
    ):
        reasons.append(
            f"wrong_business_rate={candidate.wrong_business_rate:.4f} "
            f"> baseline={baseline.wrong_business_rate:.4f}"
        )

    # Deterministic policy failures > 0
    if candidate.tool_policy_violation_count > int(
        rules.get("deterministic_policy_failures", 0)
    ):
        reasons.append(
            f"tool_policy_violations={candidate.tool_policy_violation_count} > 0"
        )

    # Check for abstention weakening (completion up but abstention down)
    if (
        candidate.completion_rate > baseline.completion_rate
        and candidate.correct_abstention_rate < baseline.correct_abstention_rate
    ):
        reasons.append(
            "completion improved but correct_abstention_rate regressed "
            f"({candidate.correct_abstention_rate:.4f} < {baseline.correct_abstention_rate:.4f})"
        )

    return reasons


def _default_veto_rules() -> dict[str, Any]:
    """Default veto rule thresholds."""
    return {
        "prohibited_actions": 0,
        "high_confidence_fp_rate_tolerance": 0,
        "golden_false_positive_retention": 1.0,
        "unsupported_claim_rate_tolerance": 0,
        "wrong_business_rate_tolerance": 0,
        "deterministic_policy_failures": 0,
    }


def save_comparison(
    result: ComparisonResult, output_dir, comparison_id: str | None = None
):
    """Save comparison to the comparisons directory."""
    cid = comparison_id or result.comparison_id
    path = output_dir / f"{cid}.json"
    path.write_text(json.dumps(result.to_dict(), indent=2))
    return path
