import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "money-machine" / "supervisor" / "launchd.py"
spec = importlib.util.spec_from_file_location("launchd_under_test", MODULE_PATH)
launchd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launchd)


def test_plist_is_persistent_and_fail_closed():
    payload = launchd.plist_payload()
    assert payload["RunAtLoad"] is True
    assert payload["KeepAlive"] is True
    assert payload["WorkingDirectory"] == str(ROOT)
    assert payload["EnvironmentVariables"]["MM_EXTERNAL_SEND_DISABLED"] == "1"
    assert "LIVE_SEND_ENABLED" not in payload["EnvironmentVariables"]
    args = payload["ProgramArguments"]
    assert "service.py" in args[1]
    assert "run" in args
    assert "--sleep" in args


def test_label_and_paths_are_user_scoped():
    assert launchd.LABEL == "ai.website-auditor.supervisor"
    assert "Library/LaunchAgents" in str(launchd.PLIST_PATH)
