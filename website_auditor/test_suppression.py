from pathlib import Path

from website_auditor.outreach.suppression import SuppressionStore


def test_email_suppression_is_normalized_and_hashed(tmp_path: Path):
    store = SuppressionStore(tmp_path / "suppression.json")
    record = store.suppress_email(" Person@Example.co.nz ", reason="opt-out", source="test")
    assert record["masked"] == "p***@example.co.nz"
    raw = (tmp_path / "suppression.json").read_text()
    assert "person@example.co.nz" not in raw
    assert store.check(email="person@example.co.nz")["suppressed"] is True


def test_domain_suppression_blocks_any_email_on_domain(tmp_path: Path):
    store = SuppressionStore(tmp_path / "suppression.json")
    store.suppress_domain("Example.co.nz", reason="do-not-contact")
    result = store.check(email="someone@example.co.nz")
    assert result["suppressed"] is True
    assert result["scope"] == "domain"


def test_unsuppress_removes_records(tmp_path: Path):
    store = SuppressionStore(tmp_path / "suppression.json")
    store.suppress_email("person@example.co.nz")
    assert store.unsuppress_email("person@example.co.nz") is True
    assert store.check(email="person@example.co.nz")["suppressed"] is False


def test_action_executor_blocks_suppressed_outreach(tmp_path: Path):
    import json

    from website_auditor.actions.executor import ActionExecutor
    from website_auditor.actions.registry import build_action

    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({
        "enabled": True,
        "execution_enabled": True,
        "mode": "supervised",
        "allow_production_changes": False,
        "allow_external_emails": True,
        "allow_external_connectors": True,
        "require_approval_risks": ["medium", "high", "critical"],
        "max_actions_per_hour": 20,
        "environments_allowed_for_auto": ["local", "staging"],
        "blocked_categories": []
    }))

    executor = ActionExecutor(tmp_path / "actions", config_path=policy)
    executor.suppression.suppress_email("person@example.co.nz", reason="opt-out", source="test")
    action = executor.propose(
        build_action(
            "outreach.send",
            domain="example.co.nz",
            payload={"recipient": "person@example.co.nz", "compliance_ok": True},
        )
    )
    executor.approve(action.action_id, actor="tester")
    executor.authorize("example.co.nz", scopes=["outreach_send"], actor="tester")

    result = executor.execute(action.action_id)
    assert result["executed"] is False
    assert result["suppression"]["suppressed"] is True
    assert "suppression" in result["decision"]["reason"].lower()
