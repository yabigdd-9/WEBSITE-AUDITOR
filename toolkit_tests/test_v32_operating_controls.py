import json
from dataclasses import replace

import pytest

from auditor_toolkit.actions.policy import PolicyEngine
from auditor_toolkit.models import Action, Risk, RiskValue
from auditor_toolkit.monitoring.watchdog import Watchdog
from auditor_toolkit.reporting.email_sender import send_report_email


@pytest.fixture
def action():
    return Action(
        action_id="fixture",
        name="Review page title",
        category="seo",
        risk=Risk(RiskValue.MEDIUM, 45),
        connector="local",
        domain="example.test",
        environment="staging",
        requires_authorization=True,
        requires_approval=True,
    )


def test_default_policy_only_prepares_a_draft(tmp_path, action):
    policy = PolicyEngine(tmp_path / "missing.json")
    assert policy.evaluate(action).to_dict() == {
        "allowed": True,
        "effect": "dry_run",
        "reason": "Dry-run mode: plan and log only.",
        "requires_approval": True,
    }
    assert not policy.evaluate(action, paused=True).allowed


def test_configured_policy_requires_authorization_and_approval(tmp_path, action):
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({
        "enabled": True,
        "mode": "review",
        "blocked_categories": ["outreach_send"],
        "require_approval_risks": ["medium"],
    }))
    policy = PolicyEngine(path)
    assert policy.evaluate(action, approved=True).reason == "Authorization required."
    assert policy.evaluate(action, authorized=True).effect == "pending_approval"
    assert policy.evaluate(action, authorized=True, approved=True).effect == "execute"
    assert not policy.evaluate(replace(action, environment="production"),
                               authorized=True, approved=True).allowed
    assert not policy.evaluate(replace(action, category="outreach_send"),
                               authorized=True, approved=True).allowed
    assert not policy.evaluate(replace(action, risk=Risk(RiskValue.LOW, 10)),
                               authorized=True).allowed
    policy.config["enabled"] = False
    assert not policy.evaluate(action, authorized=True, approved=True).allowed


def test_watchdog_compares_local_snapshots(tmp_path, monkeypatch):
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    watchdog = Watchdog(output_root=tmp_path)
    assert watchdog.detect_regressions("example.test", [])["first_audit"]
    folder = tmp_path / "snapshots"
    (folder / "example.test_20260101_000001.json").write_text(
        json.dumps({"defect_keys": ["broken-link"], "count": 1})
    )
    snapshot = watchdog.take_snapshot("example.test", [{"defect_key": "missing-title"}])
    assert snapshot.parent == folder
    assert json.loads(snapshot.read_text())["defect_keys"] == ["missing-title"]
    result = watchdog.detect_regressions("example.test", [{"defect_key": "missing-title"}])
    assert result["regressions"] == ["missing-title"]
    assert result["resolved"] == ["broken-link"]
    assert watchdog.send_alert("example.test", result["regressions"])["status"] == "skipped"


@pytest.mark.parametrize("attachment", [None, "report.pdf"])
def test_report_email_is_draft_only(attachment):
    draft = send_report_email("operator@example.test", "Audit", "Fixture", attachment)
    assert draft["status"] == "draft"
    assert draft["sent"] is False
    assert draft["attachment"] == attachment
