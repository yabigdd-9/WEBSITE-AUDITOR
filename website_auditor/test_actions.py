import json
from pathlib import Path

import pytest

from website_auditor.actions.executor import ActionExecutor
from website_auditor.actions.policy import PolicyEngine
from website_auditor.actions.registry import build_action
from website_auditor.actions.secrets import SecretResolver
from website_auditor.actions.store import KillSwitch


def policy_file(tmp_path: Path, **overrides) -> Path:
    config = {
        "enabled": True,
        "execution_enabled": False,
        "mode": "dry_run",
        "allow_production_changes": False,
        "allow_external_emails": False,
        "allow_external_connectors": False,
        "auto_approve_risks": ["low"],
        "require_approval_risks": ["medium", "high", "critical"],
        "max_actions_per_hour": 20,
        "environments_allowed_for_auto": ["local", "staging"],
        "blocked_categories": ["dns_write", "tls_install", "production_deploy", "outreach_send"],
        "secret_env_allowlist": [],
    }
    config.update(overrides)
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(config))
    return path


def test_default_policy_is_dry_run(tmp_path: Path):
    policy = PolicyEngine(policy_file(tmp_path))
    action = build_action("outreach.send", domain="example.co.nz")
    decision = policy.evaluate(action)
    assert decision.allowed is True
    assert decision.effect == "dry_run"


def test_external_email_is_blocked_in_live_mode(tmp_path: Path):
    policy = PolicyEngine(
        policy_file(
            tmp_path,
            mode="supervised",
            execution_enabled=True,
            allow_external_connectors=True,
            allow_external_emails=False,
            blocked_categories=[],
        )
    )
    action = build_action("outreach.send", domain="example.co.nz")
    decision = policy.evaluate(action, approved=True, authorized=True, compliance_ok=True)
    assert decision.allowed is False
    assert "email" in decision.reason.lower()


def test_kill_switch_blocks_actions(tmp_path: Path):
    kill = KillSwitch(tmp_path / "KILL_SWITCH")
    kill.pause("tester")
    policy = PolicyEngine(policy_file(tmp_path), kill_switch=kill)
    action = build_action("ticket.create", domain="example.co.nz")
    decision = policy.evaluate(action)
    assert decision.allowed is False
    assert "emergency" in decision.reason.lower()


def test_local_execution_and_idempotency(tmp_path: Path):
    config = policy_file(tmp_path, mode="supervised", execution_enabled=True)
    executor = ActionExecutor(tmp_path / "actions", config_path=config)
    action = executor.propose(build_action("ticket.create", domain="example.co.nz"))
    first = executor.execute(action.action_id)
    assert first["executed"] is True
    assert first["verification"]["ok"] is True
    second = executor.execute(action.action_id)
    assert second["executed"] is False
    assert second["idempotent"] is True


def test_medium_patch_requires_approval_and_authorization(tmp_path: Path):
    config = policy_file(tmp_path, mode="supervised", execution_enabled=True)
    executor = ActionExecutor(tmp_path / "actions", config_path=config)
    action = executor.propose(build_action("patch.local_stage", domain="example.co.nz"))

    blocked = executor.execute(action.action_id)
    assert blocked["executed"] is False
    assert "approval" in blocked["decision"]["reason"].lower()

    executor.approve(action.action_id, actor="tester")
    still_blocked = executor.execute(action.action_id)
    assert still_blocked["executed"] is False
    assert "authorized" in still_blocked["decision"]["reason"].lower()

    executor.authorize("example.co.nz", scopes=["remediation"], actor="tester")
    executed = executor.execute(action.action_id)
    assert executed["executed"] is True
    assert executed["verification"]["ok"] is True


def test_rollback_removes_local_artifact(tmp_path: Path):
    config = policy_file(tmp_path, mode="supervised", execution_enabled=True)
    executor = ActionExecutor(tmp_path / "actions", config_path=config)
    action = executor.propose(build_action("ticket.create", domain="example.co.nz"))
    executed = executor.execute(action.action_id)
    artifact = Path(executed["result"]["artifacts"][0])
    assert artifact.exists()
    rolled_back = executor.rollback(action.action_id)
    assert rolled_back["result"]["verification"]["artifact_absent"] is True
    assert not artifact.exists()


def test_secret_resolver_is_allowlist_only(monkeypatch):
    monkeypatch.setenv("WA_TEST_TOKEN", "secret-value")
    resolver = SecretResolver(["WA_TEST_TOKEN"])
    assert resolver.get("WA_TEST_TOKEN") == "secret-value"
    with pytest.raises(PermissionError):
        resolver.get("UNAPPROVED_TOKEN")
