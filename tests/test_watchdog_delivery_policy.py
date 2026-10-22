"""Watchdog alert previews never invoke a network transport."""
from unittest.mock import patch

from website_auditor.monitoring.watchdog import Watchdog


def test_configured_webhook_is_not_send_authorization(tmp_path, monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://fixture.invalid/webhook")
    monkeypatch.setenv("MM_EXTERNAL_SEND_DISABLED", "0")
    with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
        result = Watchdog(output_root=tmp_path).send_alert("fixture.invalid", ["fixture regression"])
    assert result["status"] == "blocked"
    assert result["sent"] is False
    assert result["network_calls"] == 0
    assert "fixture regression" in result["preview"]
    assert "webhook" not in result["preview"]


def test_unconfigured_webhook_remains_skipped(tmp_path, monkeypatch):
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    assert Watchdog(output_root=tmp_path).send_alert("fixture.invalid", []) == {
        "status": "skipped", "reason": "ALERT_WEBHOOK_URL not set"}
