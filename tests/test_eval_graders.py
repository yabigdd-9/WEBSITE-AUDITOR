"""Tests for deterministic evaluation graders."""

import json

from auditor_toolkit.evaluation.graders import (
    GRADER_REGISTRY,
    ClaimEvidenceSupportGrader,
    CorrectAbstentionGrader,
    EvidenceReferenceValidityGrader,
    FindingIdValidityGrader,
    ForbiddenActionGrader,
    GoldenCorpusRetentionGrader,
    JSONValidityGrader,
    OutputReproducibilityGrader,
    RequiredToolUsageGrader,
    SchemaValidityGrader,
    ToolPolicyComplianceGrader,
    UnsupportedClaimGrader,
    WrongBusinessGrader,
    run_all_graders,
)
from auditor_toolkit.evaluation.schema import (
    EvalCase,
    EvalEvidenceRef,
    EvalExpectedResult,
    EvalResult,
    EvalToolCall,
)


def _make_case(**overrides):
    defaults = {
        "case_id": "test_case",
        "category": "accessibility",
        "task": "test task",
        "fixture_id": "fixture_001",
        "expected_behavior": "finding",
    }
    defaults.update(overrides)
    return EvalCase(**defaults)


def _make_result(
    claims=None, evidence=None, tool_calls=None, output="", model="local"
):
    return EvalResult(
        case_id="test_case",
        run_id="run_001",
        claims=claims or [],
        evidence_selected=evidence or [],
        tool_calls=tool_calls or [],
        agent_output=output,
        agent_model=model,
    )


# --- JSON_VALIDITY ---


def test_json_validity_pass():
    grader = JSONValidityGrader()
    result = _make_result(output='{"finding_id": "f1", "severity": "high"}')
    case = _make_case()
    assert grader.grade(result, case) == "PASS"


def test_json_validity_fail():
    grader = JSONValidityGrader()
    result = _make_result(output="not valid json {{{")
    case = _make_case()
    assert grader.grade(result, case) == "FAIL"
    assert any(f.failure_class == "BROKEN_FORM" for f in result.failures)


def test_json_validity_empty():
    grader = JSONValidityGrader()
    result = _make_result(output="")
    case = _make_case()
    assert grader.grade(result, case) == "N/A"


# --- SCHEMA_VALIDITY ---


def test_schema_validity_pass():
    grader = SchemaValidityGrader()
    result = _make_result(
        output=json.dumps(
            {"finding_id": "f1", "category": "seo", "severity": "high"}
        )
    )
    case = _make_case()
    assert grader.grade(result, case) == "PASS"


def test_schema_validity_missing_keys():
    grader = SchemaValidityGrader()
    result = _make_result(output=json.dumps({"only_one": "key"}))
    case = _make_case()
    assert grader.grade(result, case) == "FAIL"


# --- FINDING_ID_VALIDITY ---


def test_finding_id_validity_pass():
    grader = FindingIdValidityGrader()
    result = _make_result(
        claims=[{"finding_id": "finding_001", "severity": "high"}]
    )
    case = _make_case(expected_findings=["finding_001"])
    assert grader.grade(result, case) == "PASS"


def test_finding_id_validity_fail():
    grader = FindingIdValidityGrader()
    result = _make_result(
        claims=[{"finding_id": "finding_999", "severity": "high"}]
    )
    case = _make_case(expected_findings=["finding_001"])
    assert grader.grade(result, case) == "FAIL"
    assert any(f.failure_class == "WRONG_FINDING_ID" for f in result.failures)


def test_finding_id_validity_no_expected():
    grader = FindingIdValidityGrader()
    result = _make_result(
        claims=[{"finding_id": "finding_001", "severity": "high"}]
    )
    case = _make_case()  # No expected_findings
    assert grader.grade(result, case) == "PASS"


# --- EVIDENCE_REFERENCE_VALIDITY ---


def test_evidence_ref_validity_pass():
    grader = EvidenceReferenceValidityGrader()
    result = _make_result(
        evidence=[EvalEvidenceRef(finding_id="f1")]
    )
    case = _make_case()
    assert grader.grade(result, case) == "PASS"


def test_evidence_ref_validity_fail():
    grader = EvidenceReferenceValidityGrader()
    result = _make_result(
        evidence=[EvalEvidenceRef(url="https://example.com")]
    )
    case = _make_case()
    assert grader.grade(result, case) == "FAIL"


# --- CLAIM_EVIDENCE_SUPPORT ---


def test_claim_evidence_support_pass():
    grader = ClaimEvidenceSupportGrader()
    result = _make_result(
        claims=[{"finding_id": "f1"}],
        evidence=[EvalEvidenceRef(finding_id="f1")],
    )
    case = _make_case()
    assert grader.grade(result, case) == "PASS"


def test_claim_evidence_support_fail():
    grader = ClaimEvidenceSupportGrader()
    result = _make_result(
        claims=[{"finding_id": "f1"}],
        evidence=[],
    )
    case = _make_case()
    assert grader.grade(result, case) == "FAIL"


# --- UNSUPPORTED_CLAIM ---


def test_unsupported_claim_pass():
    grader = UnsupportedClaimGrader()
    result = _make_result(
        claims=[{"finding_id": "f1"}],
        evidence=[EvalEvidenceRef(finding_id="f1")],
    )
    case = _make_case()
    assert grader.grade(result, case) == "PASS"


def test_unsupported_claim_fail():
    grader = UnsupportedClaimGrader()
    result = _make_result(
        claims=[{"finding_id": "f2"}],
        evidence=[EvalEvidenceRef(finding_id="f1")],
    )
    case = _make_case()
    assert grader.grade(result, case) == "FAIL"


# --- FORBIDDEN_ACTION ---


def test_forbidden_action_pass():
    grader = ForbiddenActionGrader()
    result = _make_result(
        tool_calls=[EvalToolCall(tool_name="fetch")]
    )
    case = _make_case()
    assert grader.grade(result, case) == "PASS"


def test_forbidden_action_detected():
    grader = ForbiddenActionGrader()
    result = _make_result(
        tool_calls=[EvalToolCall(tool_name="send_email", args={"to": "user@test.com"})]
    )
    case = _make_case()
    assert grader.grade(result, case) == "FAIL"


def test_forbidden_action_blocked_is_ok():
    grader = ForbiddenActionGrader()
    result = _make_result(
        tool_calls=[
            EvalToolCall(
                tool_name="send_email",
                args={"to": "user@test.com"},
                blocked=True,
                block_reason="policy",
            )
        ]
    )
    case = _make_case()
    assert grader.grade(result, case) == "PASS"


# --- TOOL_POLICY_COMPLIANCE ---


def test_tool_policy_pass():
    grader = ToolPolicyComplianceGrader()
    result = _make_result(
        tool_calls=[EvalToolCall(tool_name="fetch")]
    )
    case = _make_case(allowed_tools=["fetch", "browser"])
    assert grader.grade(result, case) == "PASS"


def test_tool_policy_fail():
    grader = ToolPolicyComplianceGrader()
    result = _make_result(
        tool_calls=[EvalToolCall(tool_name="external_tool")]
    )
    case = _make_case(allowed_tools=["fetch"])
    assert grader.grade(result, case) == "FAIL"


def test_tool_policy_no_allowed_set():
    grader = ToolPolicyComplianceGrader()
    result = _make_result(
        tool_calls=[EvalToolCall(tool_name="anything")]
    )
    case = _make_case()  # No allowed_tools
    assert grader.grade(result, case) == "PASS"


# --- REQUIRED_TOOL_USAGE ---


def test_required_tool_usage_pass():
    grader = RequiredToolUsageGrader()
    result = _make_result(
        tool_calls=[EvalToolCall(tool_name="fetch")]
    )
    case = _make_case()
    expected = EvalExpectedResult(
        case_id="test_case", tools_must_use=["fetch"]
    )
    assert grader.grade(result, case, expected) == "PASS"


def test_required_tool_usage_fail():
    grader = RequiredToolUsageGrader()
    result = _make_result(tool_calls=[])
    case = _make_case()
    expected = EvalExpectedResult(
        case_id="test_case", tools_must_use=["fetch"]
    )
    assert grader.grade(result, case, expected) == "FAIL"


# --- CORRECT_ABSTENTION ---


def test_correct_abstention_expected_and_done():
    grader = CorrectAbstentionGrader()
    result = _make_result(
        claims=[{"abstention_reason": "INSUFFICIENT_EVIDENCE"}]
    )
    case = _make_case(expected_abstention=True)
    assert grader.grade(result, case) == "PASS"


def test_correct_abstention_expected_but_not_done():
    grader = CorrectAbstentionGrader()
    result = _make_result(
        claims=[{"finding_id": "f1", "severity": "high"}]
    )
    case = _make_case(expected_abstention=True)
    assert grader.grade(result, case) == "FAIL"


def test_correct_abstention_not_expected_and_did_nothing():
    grader = CorrectAbstentionGrader()
    result = _make_result()
    case = _make_case()
    assert grader.grade(result, case) == "FAIL"


def test_correct_abstention_gathered_evidence_no_claims():
    grader = CorrectAbstentionGrader()
    result = _make_result(
        evidence=[EvalEvidenceRef(finding_id="f1")]
    )
    case = _make_case()
    assert grader.grade(result, case) == "ABSTAIN"


# --- WRONG_BUSINESS ---


def test_wrong_business_pass():
    grader = WrongBusinessGrader()
    result = _make_result(
        claims=[{"finding_id": "f1", "business_id": "biz_001"}]
    )
    case = _make_case(metadata={"business_id": "biz_001"})
    assert grader.grade(result, case) == "PASS"


def test_wrong_business_fail():
    grader = WrongBusinessGrader()
    result = _make_result(
        claims=[{"finding_id": "f1", "business_id": "biz_999"}]
    )
    case = _make_case(metadata={"business_id": "biz_001"})
    assert grader.grade(result, case) == "FAIL"


def test_wrong_business_no_metadata():
    grader = WrongBusinessGrader()
    result = _make_result(
        claims=[{"finding_id": "f1", "business_id": "biz_001"}]
    )
    case = _make_case()
    assert grader.grade(result, case) == "PASS"


# --- GOLDEN_CORPUS_RETENTION ---


def test_golden_corpus_not_golden():
    grader = GoldenCorpusRetentionGrader()
    result = _make_result()
    case = _make_case()
    assert grader.grade(result, case) == "N/A"


def test_golden_corpus_pass():
    grader = GoldenCorpusRetentionGrader()
    result = _make_result()
    case = _make_case(
        expected_behavior="no_finding",
        metadata={"golden_corpus": True},
    )
    assert grader.grade(result, case) == "PASS"


def test_golden_corpus_regression():
    grader = GoldenCorpusRetentionGrader()
    result = _make_result(
        claims=[{"finding_id": "f1", "severity": "high"}]
    )
    case = _make_case(
        expected_behavior="no_finding",
        metadata={"golden_corpus": True},
    )
    assert grader.grade(result, case) == "FAIL"


# --- OUTPUT_REPRODUCIBILITY ---


def test_output_reproducibility_no_hash():
    grader = OutputReproducibilityGrader()
    result = _make_result(output="some output")
    case = _make_case()
    assert grader.grade(result, case) == "PASS"


# --- Registry ---


def test_grader_registry_complete():
    expected_graders = {
        "JSON_VALIDITY",
        "SCHEMA_VALIDITY",
        "FINDING_ID_VALIDITY",
        "EVIDENCE_REFERENCE_VALIDITY",
        "CLAIM_EVIDENCE_SUPPORT",
        "UNSUPPORTED_CLAIM",
        "FORBIDDEN_ACTION",
        "TOOL_POLICY_COMPLIANCE",
        "REQUIRED_TOOL_USAGE",
        "CORRECT_ABSTENTION",
        "WRONG_BUSINESS",
        "GOLDEN_CORPUS_RETENTION",
        "OUTPUT_REPRODUCIBILITY",
    }
    assert set(GRADER_REGISTRY.keys()) == expected_graders


# --- run_all_graders ---


def test_run_all_graders():
    result = _make_result(
        output='{"finding_id": "finding_001", "severity": "high"}',
        claims=[{"finding_id": "finding_001", "severity": "high"}],
        evidence=[EvalEvidenceRef(finding_id="finding_001")],
        tool_calls=[EvalToolCall(tool_name="fetch")],
    )
    case = _make_case(
        expected_findings=["finding_001"],
        allowed_tools=["fetch"],
    )
    expected = EvalExpectedResult(
        case_id="test_case",
        findings=["finding_001"],
        tools_must_use=["fetch"],
    )

    run_all_graders(result, case, expected)
    assert result.overall in ("PASS", "FAIL")  # Determined by grader results
    assert len(result.grader_verdicts) >= 13
