
import mm_email_tracking as tracking
import tempfile
from pathlib import Path
import pytest


@pytest.fixture
def project_tmp_path(tmp_path_factory):
    """Create a temporary directory within the project root for testing."""
    project_root = Path(__file__).resolve().parents[1]
    return Path(tempfile.mkdtemp(dir=project_root))


def event(status="provider_accepted", kind="provider_accepted", event_id="evt-1"):
    return {
        "provider": "fixture",
        "provider_event_id": event_id,
        "message_id": "msg-1",
        "business_id": 7,
        "recipient": "Team@Example.co.nz",
        "kind": kind,
        "status": status,
    }


def test_tracking_is_idempotent_and_does_not_send(project_tmp_path):
    path = project_tmp_path / "events.jsonl"
    first = tracking.record(event(), path)
    second = tracking.record(event(), path)
    assert first["recorded"] is True
    assert second["duplicate"] is True
    assert len(path.read_text().splitlines()) == 1
    assert tracking.summary(path)["external_sends_by_this_module"] == 0


def test_tracking_reconciles_terminal_reply_without_open_tracking(project_tmp_path):
    path = project_tmp_path / "events.jsonl"
    tracking.record(event(status="provider_accepted", event_id="evt-1"), path)
    tracking.record(event(status="replied", kind="reply", event_id="evt-2"), path)
    result = tracking.reconcile("msg-1", path)
    assert result["status"] == "replied"
    assert result["terminal"] is True
    summary = tracking.summary(path)
    assert summary["open_tracking"] is False
    assert summary["click_tracking"] is False
    assert summary["status_counts"]["replied"] == 1
