"""Tests for evaluation runner."""

import json

from auditor_toolkit.evaluation.runner import (
    EvalRunner,
    _current_commit,
    _now_iso,
    _tool_versions,
    hash_fixture_content,
)
from auditor_toolkit.evaluation.schema import (
    EvalCase,
    EvalEvidenceRef,
    EvalFailure,
    EvalResult,
    EvalRun,
)


class _FakeAdapter:
    """A deterministic fake agent for testing."""

    def __init__(self, behavior="passing"):
        self.behavior = behavior

    def run(self, case, run_id=""):
        if self.behavior == "passing":
            return EvalResult(
                case_id=case.case_id,
                run_id=run_id,
                claims=[{"finding_id": fid, "severity": "high"} for fid in case.expected_findings],
                evidence_selected=[
                    EvalEvidenceRef(finding_id=fid)
                    for fid in case.expected_findings
                ],
                tool_calls=[],
                agent_output=json.dumps(
                    [{"finding_id": fid, "severity": "high", "category": case.category}
                     for fid in case.expected_findings]
                ),
                agent_model="fake",
            )
        elif self.behavior == "failing":
            return EvalResult(
                case_id=case.case_id,
                run_id=run_id,
                claims=[{"finding_id": "wrong_id", "severity": "high"}],
                evidence_selected=[],
                tool_calls=[],
                agent_output="not json",
                agent_model="fake",
            )
        elif self.behavior == "crash":
            raise RuntimeError("Agent crashed")
        elif self.behavior == "forbidden":
            from auditor_toolkit.evaluation.schema import EvalToolCall
            return EvalResult(
                case_id=case.case_id,
                run_id=run_id,
                claims=[],
                evidence_selected=[],
                tool_calls=[EvalToolCall(tool_name="send_email", args={"to": "test@test.com"})],
                agent_output="[]",
                agent_model="fake",
            )
        else:
            return EvalResult(
                case_id=case.case_id,
                run_id=run_id,
                agent_model="fake",
            )


def _make_case(cid="test_001", **kw):
    defaults = {
        "case_id": cid,
        "category": "accessibility",
        "task": "test task",
        "fixture_id": "fixture_001",
        "expected_behavior": "finding",
    }
    defaults.update(kw)
    return EvalCase(**defaults)


def test_run_single_case_pass():
    adapter = _FakeAdapter(behavior="passing")
    runner = EvalRunner(adapter=adapter)
    case = _make_case(expected_findings=["finding_001"])
    result = runner.run_case(case, run_id="run_001")
    assert result.overall == "PASS"
    assert len(result.claims) == 1


def test_run_single_case_fail():
    adapter = _FakeAdapter(behavior="failing")
    runner = EvalRunner(adapter=adapter)
    case = _make_case(expected_findings=["finding_001"])
    result = runner.run_case(case, run_id="run_001")
    assert result.overall == "FAIL"


def test_run_single_case_crash():
    adapter = _FakeAdapter(behavior="crash")
    runner = EvalRunner(adapter=adapter)
    case = _make_case()
    result = runner.run_case(case, run_id="run_001")
    assert result.overall == "FAIL"
    assert "ERROR" in result.agent_output


def test_run_single_case_forbidden():
    adapter = _FakeAdapter(behavior="forbidden")
    runner = EvalRunner(adapter=adapter)
    case = _make_case()
    result = runner.run_case(case, run_id="run_001")
    assert result.overall == "FAIL"


def test_run_suite():
    adapter = _FakeAdapter(behavior="passing")
    runner = EvalRunner(adapter=adapter)
    cases = [
        _make_case(cid="c1", expected_findings=["f1"]),
        _make_case(cid="c2", expected_findings=["f2"]),
    ]
    run = runner.run_suite(
        cases,
        candidate_id="test-candidate",
        model_name="fake",
        agent_version="0.1.0",
    )
    assert run.total == 2
    assert run.pass_count == 2
    assert run.status == "COMPLETE"
    assert run.model_name == "fake"


def test_run_suite_mixed():
    adapter_pass = _FakeAdapter(behavior="passing")

    # Run suite with passing adapter
    runner = EvalRunner(adapter=adapter_pass)
    cases = [
        _make_case(cid="c1", expected_findings=["f1"]),
        _make_case(cid="c2", expected_findings=["f2"]),
    ]
    run = runner.run_suite(
        cases,
        candidate_id="test-candidate",
        model_name="fake",
    )
    assert run.total == 2
    assert run.pass_count == 2


def test_compute_metrics():
    adapter = _FakeAdapter(behavior="passing")
    runner = EvalRunner(adapter=adapter)
    cases = [_make_case(cid="c1", expected_findings=["f1"])]
    run = runner.run_suite(cases, model_name="fake")
    metrics = runner.compute_metrics(run)
    assert metrics.total_cases == 1
    assert metrics.pass_count == 1
    assert metrics.completion_rate == 1.0


def test_compute_metrics_aggregates_claims_abstentions_and_failures():
    runner = EvalRunner(adapter=_FakeAdapter())
    run = EvalRun(
        run_id="run-metrics",
        candidate_id="candidate",
        baseline_id="baseline",
        model_name="fake",
        agent_version="1",
        repository_commit="abc",
        policy_version="1",
        results=[
            EvalResult(
                case_id="supported",
                run_id="run-metrics",
                overall="PASS",
                claims=[{"evidence_id": "e1"}, {"text": "unsupported"}],
                duration_ms=100,
            ),
            EvalResult(
                case_id="evidence-abstention",
                run_id="run-metrics",
                overall="ABSTAIN",
                evidence_selected=[EvalEvidenceRef(evidence_id="e2")],
                duration_ms=300,
                failures=[
                    EvalFailure("GOLDEN_CORPUS_REGRESSION", "c2", "g", "regression"),
                    EvalFailure("FORBIDDEN_ACTION", "c2", "g", "blocked"),
                    EvalFailure("TOOL_POLICY_VIOLATION", "c2", "g", "policy"),
                ],
            ),
            EvalResult(
                case_id="empty-abstention",
                run_id="run-metrics",
                overall="N/A",
                duration_ms=200,
            ),
        ],
    )

    metrics = runner.compute_metrics(run)

    assert metrics.unsupported_claim_rate == 0.5
    assert metrics.correct_abstention_rate == 0.5
    assert metrics.incorrect_abstention_rate == 0.5
    assert metrics.avg_latency_ms == 200
    assert metrics.golden_corpus_retention == 0.99
    assert metrics.prohibited_action_count == 1
    assert metrics.tool_policy_violation_count == 1


def test_save_run(tmp_path):
    adapter = _FakeAdapter(behavior="passing")
    output_dir = tmp_path / "runs"
    runner = EvalRunner(adapter=adapter, output_dir=output_dir)
    cases = [_make_case(cid="c1", expected_findings=["f1"])]
    run = runner.run_suite(cases, model_name="fake")
    metrics = runner.compute_metrics(run)
    result_dir = runner.save_run(run, metrics)

    assert result_dir is not None
    assert (result_dir / "manifest.json").exists()
    assert (result_dir / "results.json").exists()
    assert (result_dir / "metrics.json").exists()
    assert (result_dir / "failures.json").exists()
    assert (result_dir / "tool_calls.jsonl").exists()


def test_now_iso():
    ts = _now_iso()
    assert "T" in ts


def test_current_commit():
    commit = _current_commit()
    assert commit != ""  # Should resolve in a git repo


def test_tool_versions():
    versions = _tool_versions()
    assert isinstance(versions, dict)


def test_hash_fixture_content():
    h1 = hash_fixture_content("hello")
    h2 = hash_fixture_content("hello")
    h3 = hash_fixture_content("world")
    assert h1 == h2
    assert h1 != h3
