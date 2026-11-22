"""Tests for evaluation comparison and regression veto."""

from auditor_toolkit.evaluation.comparison import (
    _check_veto_rules,
    _compute_deltas,
    compare,
    save_comparison,
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


def test_compare_candidate_better():
    baseline = _make_metrics(run_id="baseline")
    candidate = _make_metrics(
        run_id="candidate",
        finding_precision=0.90,
        finding_recall=0.85,
        avg_latency_ms=800.0,
    )

    result = compare(candidate, baseline)
    assert not result.veto_triggered
    assert result.recommended_action == "PROMOTION_ELIGIBLE"
    assert len(result.deltas) > 0


def test_compare_candidate_worse():
    baseline = _make_metrics(run_id="baseline")
    candidate = _make_metrics(
        run_id="candidate",
        finding_precision=0.60,
        high_confidence_fp_rate=0.10,
    )

    result = compare(candidate, baseline)
    # FP rate regression should trigger veto
    assert result.veto_triggered
    assert result.recommended_action == "REJECT"


def test_compare_identical():
    m = _make_metrics(run_id="run")
    result = compare(m, m)
    assert not result.veto_triggered
    assert result.recommended_action == "PROMOTION_ELIGIBLE"


def test_veto_prohibited_actions():
    baseline = _make_metrics(run_id="baseline")
    candidate = _make_metrics(
        run_id="candidate",
        prohibited_action_count=1,
    )

    reasons = _check_veto_rules(candidate, baseline)
    assert any("prohibited_actions" in r for r in reasons)


def test_veto_golden_corpus_retention():
    baseline = _make_metrics(run_id="baseline")
    candidate = _make_metrics(
        run_id="candidate",
        golden_corpus_retention=0.85,
    )

    reasons = _check_veto_rules(candidate, baseline)
    assert any("golden_corpus_retention" in r for r in reasons)


def test_veto_high_confidence_fp_rate():
    baseline = _make_metrics(
        run_id="baseline",
        high_confidence_fp_rate=0.02,
    )
    candidate = _make_metrics(
        run_id="candidate",
        high_confidence_fp_rate=0.07,
    )

    reasons = _check_veto_rules(candidate, baseline)
    assert any("high_confidence_fp_rate" in r for r in reasons)


def test_veto_unsupported_claim_rate():
    baseline = _make_metrics(
        run_id="baseline",
        unsupported_claim_rate=0.05,
    )
    candidate = _make_metrics(
        run_id="candidate",
        unsupported_claim_rate=0.12,
    )

    reasons = _check_veto_rules(candidate, baseline)
    assert any("unsupported_claim_rate" in r for r in reasons)


def test_veto_wrong_business_rate():
    baseline = _make_metrics(
        run_id="baseline",
        wrong_business_rate=0.0,
    )
    candidate = _make_metrics(
        run_id="candidate",
        wrong_business_rate=0.05,
    )

    reasons = _check_veto_rules(candidate, baseline)
    assert any("wrong_business_rate" in r for r in reasons)


def test_veto_tool_policy_violations():
    baseline = _make_metrics(run_id="baseline")
    candidate = _make_metrics(
        run_id="candidate",
        tool_policy_violation_count=2,
    )

    reasons = _check_veto_rules(candidate, baseline)
    assert any("tool_policy_violations" in r for r in reasons)


def test_veto_abstention_weakening():
    """Candidate improves completion by weakening abstention — should veto."""
    baseline = _make_metrics(
        run_id="baseline",
        completion_rate=0.78,
        correct_abstention_rate=0.90,
    )
    candidate = _make_metrics(
        run_id="candidate",
        completion_rate=0.92,
        correct_abstention_rate=0.60,
    )

    reasons = _check_veto_rules(candidate, baseline)
    assert any("abstention" in r.lower() for r in reasons)


def test_no_veto_when_safe():
    baseline = _make_metrics(run_id="baseline")
    candidate = _make_metrics(
        run_id="candidate",
        finding_precision=0.85,
        avg_latency_ms=900.0,
    )

    reasons = _check_veto_rules(candidate, baseline)
    assert reasons == []


def test_compute_deltas():
    baseline = _make_metrics(run_id="baseline")
    candidate = _make_metrics(
        run_id="candidate",
        finding_precision=0.90,
    )

    deltas = _compute_deltas(candidate, baseline)
    precision_delta = next(d for d in deltas if d.metric == "finding_precision")
    assert precision_delta.delta == 0.10
    assert precision_delta.direction == "improved"


def test_compute_deltas_higher_is_better():
    baseline = _make_metrics(run_id="baseline", finding_recall=0.50)
    candidate = _make_metrics(run_id="candidate", finding_recall=0.70)

    deltas = _compute_deltas(candidate, baseline)
    recall_delta = next(d for d in deltas if d.metric == "finding_recall")
    assert recall_delta.direction == "improved"


def test_compute_deltas_lower_is_better():
    baseline = _make_metrics(run_id="baseline", avg_latency_ms=1000)
    candidate = _make_metrics(run_id="candidate", avg_latency_ms=500)

    deltas = _compute_deltas(candidate, baseline)
    latency_delta = next(d for d in deltas if d.metric == "avg_latency_ms")
    assert latency_delta.direction == "improved"


def test_save_comparison(tmp_path):
    baseline = _make_metrics(run_id="baseline")
    candidate = _make_metrics(run_id="candidate")

    result = compare(candidate, baseline)
    path = save_comparison(result, tmp_path, "test_cmp")

    assert path.exists()
    assert path.name == "test_cmp.json"
    import json
    data = json.loads(path.read_text())
    assert "deltas" in data
    assert "candidate_metrics" in data
