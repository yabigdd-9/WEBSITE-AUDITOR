import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
OUTREACH = ROOT / "outreach"
if str(OUTREACH) not in sys.path:
    sys.path.insert(0, str(OUTREACH))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


gate = load("execution_gate", OUTREACH / "execution_gate.py")
catalyx = load("catalyx_send", OUTREACH / "catalyx_send.py")
gmail = load("legacy_gmail_send", OUTREACH / "send.py")
legacy_builder = load("legacy_monthly_builder", ROOT / "make_monthly_reporting.py")


def test_external_release_gate_is_fail_closed():
    with pytest.raises(PermissionError, match="HUMAN_APPROVAL_REQUIRED"):
        gate.require_external_release()


def test_legacy_smtp_sender_never_reaches_network():
    with patch.object(catalyx.smtplib, "SMTP", side_effect=AssertionError("network must not run")):
        with pytest.raises(PermissionError, match="HUMAN_APPROVAL_REQUIRED"):
            catalyx.send_email("fixture@example.co.nz", "fixture", "fixture", app_pw="unused")


def test_legacy_gmail_sender_never_reaches_transport():
    with pytest.raises(PermissionError, match="HUMAN_APPROVAL_REQUIRED"):
        gmail.send([], approved=True)


def test_legacy_monthly_generator_is_retired_and_does_not_write(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert legacy_builder.main() == 2
    assert not (tmp_path / "website_auditor").exists()
