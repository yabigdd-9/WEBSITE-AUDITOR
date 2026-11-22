"""E2E tests for AI evaluation harness with browser adapter stub."""


from auditor_toolkit.evaluation.adapters.browser_agent import (
    BrowserAgentAdapter,
    create_write_block_route_handler,
)
from auditor_toolkit.evaluation.policy import DEFAULT_POLICY, EvalPolicy
from auditor_toolkit.evaluation.runner import EvalRunner
from auditor_toolkit.evaluation.schema import EvalCase


def _make_case(**overrides):
    defaults = {
        "case_id": "e2e_001",
        "category": "technical",
        "task": "e2e browser test",
        "fixture_id": "clean-control",
        "expected_behavior": "pass",
    }
    defaults.update(overrides)
    return EvalCase(**defaults)


def test_browser_adapter_stub_returns_fail():
    """The browser adapter is a stub and should return FAIL gracefully."""
    adapter = BrowserAgentAdapter()
    assert not adapter.available

    case = _make_case()
    result = adapter.run(case, run_id="e2e_stub")

    assert result.overall == "FAIL"
    assert "STUB" in result.agent_output


def test_browser_adapter_in_runner():
    """Runner should handle browser adapter failures gracefully."""
    adapter = BrowserAgentAdapter()
    runner = EvalRunner(adapter=adapter)
    case = _make_case()

    result = runner.run_case(case, run_id="e2e_runner")
    # Runner should grade it — the stub returns FAIL but that's expected
    assert result.overall in ("FAIL", "N/A")


def test_write_block_route_handler_exists():
    """The write block route handler factory should return a callable."""
    handler = create_write_block_route_handler(DEFAULT_POLICY)
    assert callable(handler)


def test_write_block_with_custom_policy():
    """Custom policy with restricted approved hosts."""
    policy = EvalPolicy(
        approved_fixture_hosts=frozenset({"localhost"}),
        forbidden_write_verbs=frozenset({"POST", "DELETE"}),
    )
    handler = create_write_block_route_handler(policy)
    assert callable(handler)


def test_browser_adapter_with_forbidden_case():
    """Browser adapter should handle a case with forbidden actions."""
    adapter = BrowserAgentAdapter()
    case = _make_case(
        case_id="e2e_forbidden",
        forbidden_actions=["send_email", "deploy"],
    )
    result = adapter.run(case, run_id="e2e_forbidden_run")
    # Stub doesn't evaluate — just returns FAIL
    assert result.overall == "FAIL"
