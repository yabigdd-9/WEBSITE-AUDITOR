"""Tests for evaluation policy rules."""

from auditor_toolkit.evaluation.policy import (
    DEFAULT_POLICY,
    FORBIDDEN_EVALUATION_ACTIONS,
    FORBIDDEN_WRITE_VERBS,
    VALID_ABSTENTION_REASONS,
    EvalPolicy,
    is_approved_write_target,
    is_deterministic_grader,
    is_forbidden_action,
    is_forbidden_write_verb,
    is_valid_abstention_reason,
)


def test_default_policy_version():
    assert DEFAULT_POLICY.version == "v36"


def test_forbidden_write_verbs():
    assert "POST" in FORBIDDEN_WRITE_VERBS
    assert "PUT" in FORBIDDEN_WRITE_VERBS
    assert "PATCH" in FORBIDDEN_WRITE_VERBS
    assert "DELETE" in FORBIDDEN_WRITE_VERBS
    assert "GET" not in FORBIDDEN_WRITE_VERBS


def test_forbidden_actions():
    assert "send_email" in FORBIDDEN_EVALUATION_ACTIONS
    assert "deploy" in FORBIDDEN_EVALUATION_ACTIONS
    assert "fetch" not in FORBIDDEN_EVALUATION_ACTIONS


def test_valid_abstention_reasons():
    assert "INSUFFICIENT_EVIDENCE" in VALID_ABSTENTION_REASONS
    assert "UNVERIFIABLE" in VALID_ABSTENTION_REASONS
    assert "CONTRADICTED" in VALID_ABSTENTION_REASONS
    assert "JUST_GUESSING" not in VALID_ABSTENTION_REASONS


def test_is_deterministic_grader():
    assert is_deterministic_grader("FORBIDDEN_ACTION")
    assert is_deterministic_grader("FINDING_ID_VALIDITY")
    assert is_deterministic_grader("WRONG_BUSINESS")
    assert not is_deterministic_grader("JSON_VALIDITY")
    assert not is_deterministic_grader("CORRECT_ABSTENTION")


def test_is_forbidden_action():
    assert is_forbidden_action("send_email")
    assert is_forbidden_action("deploy")
    assert not is_forbidden_action("fetch")


def test_is_forbidden_write_verb():
    assert is_forbidden_write_verb("POST")
    assert is_forbidden_write_verb("delete")  # case-insensitive
    assert not is_forbidden_write_verb("GET")


def test_is_valid_abstention_reason():
    assert is_valid_abstention_reason("INSUFFICIENT_EVIDENCE")
    assert is_valid_abstention_reason("CONTRADICTED")
    assert not is_valid_abstention_reason("LAZY")


def test_is_approved_write_target():
    assert is_approved_write_target("http://localhost/api")
    assert is_approved_write_target("http://127.0.0.1:8080/test")
    assert not is_approved_write_target("https://example.com/api")
    assert not is_approved_write_target("https://prod.example.com/deploy")


def test_policy_to_dict():
    d = DEFAULT_POLICY.to_dict()
    assert isinstance(d["forbidden_write_verbs"], list)
    assert isinstance(d["forbidden_actions"], list)
    assert isinstance(d["valid_abstention_reasons"], list)
    assert isinstance(d["deterministic_graders"], list)
    # Should be sorted
    assert d["forbidden_write_verbs"] == sorted(d["forbidden_write_verbs"])


def test_custom_policy():
    policy = EvalPolicy(
        max_case_runtime_ms=30_000,
        max_tool_calls=20,
    )
    assert policy.max_case_runtime_ms == 30_000
    assert policy.max_tool_calls == 20
    # Should inherit defaults for other fields
    assert "send_email" in policy.forbidden_actions


def test_custom_approved_hosts():
    policy = EvalPolicy(
        approved_fixture_hosts=frozenset({"localhost", "staging.test"})
    )
    assert is_approved_write_target("http://staging.test/api", policy)
    assert not is_approved_write_target("http://prod.test/api", policy)
