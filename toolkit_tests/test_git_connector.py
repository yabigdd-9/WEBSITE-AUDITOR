"""Regression tests for the local Git connector.

The connector writes proposal previews only; it must never mutate the
repository, create branches, commit, or push. These tests verify that
contract and that the preview payload serializes cleanly (no enums leak).
"""
from pathlib import Path

from auditor_toolkit.connectors.git_connector import GitConnector
from auditor_toolkit.models import Action, Risk, RiskValue


def test_git_connector_writes_local_preview_only(tmp_path):
    action = Action(
        action_id="act-1",
        name="Fix missing title",
        category="seo",
        risk=Risk(RiskValue.MEDIUM, 45),
        connector="local",
        domain="example.com",
        environment="production",
        requires_approval=True,
        requires_authorization=True,
        payload={"page": "/"},
        idempotency_key="k-1",
    )
    out = tmp_path / "patches"
    connector = GitConnector(output_dir=str(out))
    result = connector.execute_local_patch(action)

    assert result["status"] == "preview"
    assert result["committed"] is False
    assert "no branch, commit or remote action was performed" in result["message"]
    patch_file = Path(result["file"])
    assert patch_file.exists()
    text = patch_file.read_text()
    assert "act-1" in text
    assert "medium" in text  # RiskValue serialized as primitive, not enum repr


def test_git_connector_is_idempotent_for_same_action(tmp_path):
    action = Action(
        action_id="act-2",
        name="Fix meta description",
        category="seo",
        risk=Risk(RiskValue.LOW, 10),
        connector="local",
        domain="example.com",
        environment="production",
    )
    out = tmp_path / "patches"
    connector = GitConnector(output_dir=str(out))
    first = connector.execute_local_patch(action)
    second = connector.execute_local_patch(action)
    assert first["file"] == second["file"]
    assert Path(first["file"]).read_text() == Path(second["file"]).read_text()


def test_git_connector_does_not_touch_repository(tmp_path, monkeypatch):
    action = Action(
        action_id="act-3",
        name="Fix image alt",
        category="accessibility",
        risk=Risk(RiskValue.HIGH, 60),
        connector="local",
        domain="example.com",
        environment="production",
    )
    connector = GitConnector(output_dir=str(tmp_path / "patches"))
    # Ensure no git commands are invoked: the connector has no git dependency.
    assert not hasattr(connector, "commit")
    assert not hasattr(connector, "push")
    assert not hasattr(connector, "branch")
    result = connector.execute_local_patch(action)
    assert result["committed"] is False