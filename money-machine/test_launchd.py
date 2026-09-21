import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "money-machine" / "supervisor" / "launchd.py"
SPEC = importlib.util.spec_from_file_location("launchd_under_test", MODULE_PATH)
launchd = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launchd)


def test_plist_targets_current_supervisor_cli_and_fails_closed():
    payload = launchd.plist_payload()
    args = payload["ProgramArguments"]

    assert payload["RunAtLoad"] is True
    assert payload["KeepAlive"] is True
    assert payload["WorkingDirectory"] == str(ROOT / "money-machine")
    assert payload["EnvironmentVariables"]["MM_EXTERNAL_SEND_DISABLED"] == "1"
    assert "LIVE_SEND_ENABLED" not in payload["EnvironmentVariables"]

    assert args[1:4] == ["-m", "supervisor.cli", "_run-foreground"]
    assert "--sleep" in args
    assert "--lease" in args
    assert "--rotate-every" in args


def test_launchd_is_user_scoped():
    assert launchd.LABEL == "ai.website-auditor.supervisor"
    assert "Library/LaunchAgents" in str(launchd.PLIST_PATH)
