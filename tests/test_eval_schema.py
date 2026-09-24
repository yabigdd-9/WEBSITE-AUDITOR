"""Tests for evaluation schema data models."""


from auditor_toolkit.evaluation.schema import (
    EvalCase,
    EvalEvidenceRef,
    EvalFailure,
    EvalMetrics,
    EvalResult,
    EvalRun,
    EvalToolCall,
)


def test_eval_case_creation():
    case = EvalCase(
        case_id="test_001",
        category="accessibility",
        task="Detect missing alt text",
        fixture_id="clean-control",
        expected_behavior="finding with evidence",
    )
    assert case.case_id == "test_001"
    assert case.category == "accessibility"
    assert not case.expected_abstention
    assert case.allowed_tools == []


def test_eval_case_to_dict():
    case = EvalCase(
        case_id="test_001",
        category="seo",
        task="Check meta tags",
        fixture_id="malformed-schema",
        expected_behavior="flag missing meta",
        allowed_tools=["fetch"],
        forbidden_actions=["send_email"],
        metadata={"business_id": "biz_001"},
    )
    d = case.to_dict()
    assert d["case_id"] == "test_001"
    assert d["allowed_tools"] == ["fetch"]
    assert d["metadata"]["business_id"] == "biz_001"


def test_eval_evidence_ref_provenance():
    # Has provenance
    ref = EvalEvidenceRef(finding_id="finding_001")
    assert ref.has_provenance()

    ref2 = EvalEvidenceRef(evidence_id="ev_001")
    assert ref2.has_provenance()

    # No provenance
    ref3 = EvalEvidenceRef(url="https://example.com")
    assert not ref3.has_provenance()


def test_eval_tool_call():
    tc = EvalToolCall(
        tool_name="fetch",
        args={"url": "https://example.com"},
        result_summary="200 OK",
        duration_ms=150,
    )
    assert tc.tool_name == "fetch"
    assert tc.args["url"] == "https://example.com"
    assert not tc.blocked


def test_eval_failure():
    failure = EvalFailure(
        failure_class="FORBIDDEN_ACTION",
        case_id="test_001",
        grader="FORBIDDEN_ACTION",
        message="Agent executed forbidden action: send_email",
        severity="critical",
    )
    assert failure.failure_class == "FORBIDDEN_ACTION"
    assert failure.severity == "critical"


def test_eval_result_grading():
    result = EvalResult(
        case_id="test_001",
        run_id="run_001",
    )
    result.add_grader("JSON_VALIDITY", "PASS")
    result.add_grader("SCHEMA_VALIDITY", "PASS")
    result.determine_overall()
    assert result.overall == "PASS"


def test_eval_result_deterministic_override():
    result = EvalResult(
        case_id="test_001",
        run_id="run_001",
    )
    result.add_grader("JSON_VALIDITY", "PASS")
    result.add_grader("SCHEMA_VALIDITY", "PASS")
    result.add_failure(
        EvalFailure(
            failure_class="FORBIDDEN_ACTION",
            case_id="test_001",
            grader="FORBIDDEN_ACTION",
            message="forbidden action detected",
            severity="critical",
        )
    )
    result.determine_overall()
    assert result.overall == "FAIL"


def test_eval_result_to_dict():
    result = EvalResult(
        case_id="test_001",
        run_id="run_001",
        overall="PASS",
        duration_ms=500,
        agent_model="local",
    )
    d = result.to_dict()
    assert d["case_id"] == "test_001"
    assert d["overall"] == "PASS"
    assert d["duration_ms"] == 500


def test_eval_run_tracking():
    run = EvalRun(
        run_id="run_001",
        candidate_id="candidate-v1",
        baseline_id="baseline-v1",
        model_name="local",
        agent_version="0.1.0",
        repository_commit="abc123",
        policy_version="v36",
    )
    r1 = EvalResult(case_id="case_1", run_id="run_001", overall="PASS")
    r2 = EvalResult(case_id="case_2", run_id="run_001", overall="FAIL")
    run.add_result(r1)
    run.add_result(r2)

    assert run.total == 2
    assert run.pass_count == 1
    assert run.fail_count == 1
    assert run.status == "RUNNING"


def test_eval_run_to_dict():
    run = EvalRun(
        run_id="run_001",
        candidate_id="c1",
        baseline_id="b1",
        model_name="local",
        agent_version="0.1",
        repository_commit="abc",
        policy_version="v36",
    )
    d = run.to_dict()
    assert d["run_id"] == "run_001"
    assert run.total == 0


def test_eval_metrics():
    metrics = EvalMetrics(
        run_id="run_001",
        total_cases=10,
        pass_count=7,
        fail_count=2,
        abstain_count=1,
        finding_precision=0.85,
        golden_corpus_retention=1.0,
    )
    d = metrics.to_dict()
    assert d["total_cases"] == 10
    assert d["finding_precision"] == 0.85


def test_eval_metrics_defaults():
    metrics = EvalMetrics(run_id="run_001")
    assert metrics.golden_corpus_retention == 1.0
    assert metrics.prohibited_action_count == 0
    assert metrics.local_free_model is True


def test_eval_result_abstain_overall():
    result = EvalResult(case_id="test", run_id="run")
    result.add_grader("CORRECT_ABSTENTION", "ABSTAIN")
    result.determine_overall()
    assert result.overall == "ABSTAIN"


def test_eval_result_no_graders():
    result = EvalResult(case_id="test", run_id="run")
    result.determine_overall()
    assert result.overall == "N/A"


def test_eval_case_load_from_json(tmp_path):
    case_data = {
        "case_id": "json_case",
        "category": "technical",
        "task": "Test case from JSON",
        "fixture_id": "clean-control",
        "expected_behavior": "pass",
        "allowed_tools": ["fetch"],
        "expected_findings": ["finding_001"],
        "metadata": {"business_id": "biz_test"},
    }
    case = EvalCase(**case_data)
    assert case.case_id == "json_case"
    assert case.allowed_tools == ["fetch"]
