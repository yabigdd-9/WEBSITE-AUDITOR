import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "money-machine" / "supervisor" / "launchd.py"
SPEC = importlib.util.spec_from_file_location("launchd_under_test", MODULE_PATH)
launchd = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launchd)


def test_plist_periodically_calls_idempotent_ensure_running():
    payload = launchd.plist_payload()
    args = payload["ProgramArguments"]

    assert payload["RunAtLoad"] is True
    assert payload["StartInterval"] == 300
    assert "KeepAlive" not in payload
    assert payload["WorkingDirectory"] == str(ROOT)
    assert payload["EnvironmentVariables"]["MM_EXTERNAL_SEND_DISABLED"] == "1"
    assert payload["EnvironmentVariables"]["MM_PYTHON"] == str(ROOT / ".venv-email" / "bin" / "python")
    assert "LIVE_SEND_ENABLED" not in payload["EnvironmentVariables"]

    assert args == [
        "/bin/sh",
        "-c",
        'exec "$MM_ROOT/money-machine/mm" supervisor ensure-running',
    ]


def test_launchd_check_interval_is_bounded():
    import pytest

    with pytest.raises(ValueError, match="at least 30 seconds"):
        launchd.plist_payload(interval_seconds=5)


def test_launchd_is_user_scoped():
    assert launchd.LABEL == "ai.website-auditor.supervisor"
    assert "Library/LaunchAgents" in str(launchd.PLIST_PATH)
