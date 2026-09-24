"""Tests for evaluation report generation."""

import json

from auditor_toolkit.evaluation.comparison import compare
from auditor_toolkit.evaluation.promotion import create_proposal
from auditor_toolkit.evaluation.report import (
    BenchmarkReport,
    _acceptance_summary,
    _compute_gates,
    generate_benchmark,
    save_benchmark_json,
    save_benchmark_markdown,
)
from auditor_toolkit.evaluation.schema import EvalMetrics, EvalRun


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


def _make_run(**overrides):
    defaults = {
        "run_id": "run_001",
        "candidate_id": "candidate-v1",
        "baseline_id": "baseline-v1",
        "model_name": "local",
        "agent_version": "0.1.0",
        "repository_commit": "abc123",
        "policy_version": "v36",
    }
    defaults.update(overrides)
    return EvalRun(**defaults)


def test_generate_benchmark_self_comparison():
    run = _make_run()
    metrics = _make_metrics(run_id="run_001")

    report = generate_benchmark(run, metrics)
    assert report.benchmark_version == "v36"
    # total_cases comes from the EvalRun (which has no results added),
    # but metrics has total_cases set
    assert report.total_cases == 0  # EvalRun has no results
    assert report.candidate_pass == 0


def test_generate_benchmark_with_baseline():
    run = _make_run()
    metrics = _make_metrics(run_id="candidate")
    baseline = _make_metrics(run_id="baseline")

    report = generate_benchmark(
        run, metrics, baseline_metrics=baseline, benchmark_version="v36-test"
    )
    assert report.benchmark_version == "v36-test"
    assert report.comparison is not None
    assert not report.comparison.veto_triggered


def test_compute_gates_all_pass():
    candidate = _make_metrics(
        finding_precision=0.96,
        unsupported_claim_rate=0.0,
        high_confidence_fp_rate=0.0,
        wrong_business_rate=0.0,
        correct_abstention_rate=0.95,
    )
    baseline = _make_metrics(
        finding_precision=0.80,
        unsupported_claim_rate=0.10,
        high_confidence_fp_rate=0.05,
        wrong_business_rate=0.02,
        correct_abstention_rate=0.80,
    )

    gates = _compute_gates(candidate, baseline)
    assert len(gates) == 15
    assert all(gates.values())


def test_compute_gates_irreversible_actions_fail():
    candidate = _make_metrics(prohibited_action_count=1)
    baseline = _make_metrics()

    gates = _compute_gates(candidate, baseline)
    assert not gates["gate_01_no_irreversible_actions"]


def test_compute_gates_golden_retention_fail():
    candidate = _make_metrics(golden_corpus_retention=0.80)
    baseline = _make_metrics()

    gates = _compute_gates(candidate, baseline)
    assert not gates["gate_04_golden_false_positive_retention"]


def test_acceptance_summary():
    metrics = _make_metrics(
        finding_precision=0.96,
        unsupported_claim_rate=0.0,
        high_confidence_fp_rate=0.0,
        wrong_business_rate=0.0,
        correct_abstention_rate=0.95,
    )
    baseline = _make_metrics(
        finding_precision=0.80,
        unsupported_claim_rate=0.10,
        high_confidence_fp_rate=0.05,
        wrong_business_rate=0.02,
        correct_abstention_rate=0.80,
    )
    gates = _compute_gates(metrics, baseline)

    summary = _acceptance_summary(metrics, gates)
    assert "ALL GATES PASSED" in summary
    assert "FP rate:" in summary
    assert "Golden retention:" in summary


def test_acceptance_summary_partial():
    metrics = _make_metrics(prohibited_action_count=1)
    baseline = _make_metrics()
    gates = _compute_gates(metrics, baseline)

    summary = _acceptance_summary(metrics, gates)
    assert "ALL GATES PASSED" not in summary
    assert "GATES PASSED" in summary


def test_save_benchmark_json(tmp_path):
    run = _make_run()
    metrics = _make_metrics()

    report = generate_benchmark(run, metrics)
    path = save_benchmark_json(report, tmp_path)

    assert path.exists()
    data = json.loads(path.read_text())
    assert data["benchmark_version"] == "v36"


def test_save_benchmark_markdown(tmp_path):
    run = _make_run()
    metrics = _make_metrics()

    report = generate_benchmark(run, metrics)
    path = save_benchmark_markdown(report, tmp_path)

    assert path.exists()
    content = path.read_text()
    assert "# P1-007 v36" in content
    assert "Acceptance Gates" in content
    assert "Safety Attestation" in content


def test_benchmark_report_to_dict():
    run = _make_run()
    metrics = _make_metrics()
    report = generate_benchmark(run, metrics)

    d = report.to_dict()
    assert "benchmark_version" in d
    assert "candidate_metrics" in d
    assert "gates" in d


def test_benchmark_with_promotion(tmp_path):
    metrics = _make_metrics(
        run_id="candidate",
        finding_precision=0.96,
        unsupported_claim_rate=0.0,
        high_confidence_fp_rate=0.0,
        wrong_business_rate=0.0,
        correct_abstention_rate=0.95,
        golden_corpus_retention=1.0,
        prohibited_action_count=0,
        tool_policy_violation_count=0,
    )
    baseline = _make_metrics(
        run_id="baseline",
        finding_precision=0.80,
        unsupported_claim_rate=0.10,
        high_confidence_fp_rate=0.05,
        wrong_business_rate=0.02,
        correct_abstention_rate=0.80,
    )

    comparison = compare(metrics, baseline)
    gates = _compute_gates(metrics, baseline)
    proposal = create_proposal(comparison, gate_results=gates)

    report = BenchmarkReport(
        benchmark_version="v36",
        candidate_id="candidate",
        baseline_id="baseline",
        total_cases=10,
        candidate_pass=8,
        candidate_fail=2,
        candidate_metrics=metrics,
        baseline_metrics=baseline,
        comparison=comparison,
        promotion=proposal,
        gates=gates,
    )

    path = save_benchmark_json(report, tmp_path)
    data = json.loads(path.read_text())
    assert data["promotion"] is not None
    assert data["promotion"]["recommended_action"] == "PROMOTION_ELIGIBLE"
