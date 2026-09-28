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


FCC_MODULE_PATH = ROOT / "money-machine" / "supervisor" / "fcc_launchd.py"
FCC_SPEC = importlib.util.spec_from_file_location("fcc_launchd_under_test", FCC_MODULE_PATH)
fcc_launchd = importlib.util.module_from_spec(FCC_SPEC)
FCC_SPEC.loader.exec_module(fcc_launchd)


def test_fcc_plist_is_loopback_user_scoped_and_keepalive():
    payload = fcc_launchd.plist_payload()
    assert payload["RunAtLoad"] is True
    assert payload["KeepAlive"] is True
    assert payload["WorkingDirectory"] == str(ROOT)
    assert payload["EnvironmentVariables"]["HOST"] == "127.0.0.1"
    assert payload["EnvironmentVariables"]["PORT"] == "8082"
    assert payload["ProgramArguments"] == [
        "/bin/sh", str(ROOT / "scripts" / "fcc-server-wrapper.sh")
    ]
    assert fcc_launchd.LABEL == "ai.website-auditor.fcc"
    assert "Library/LaunchAgents" in str(fcc_launchd.PLIST_PATH)


def test_money_machine_python_path_prefers_project_venvs():
    path = launchd.python_path()
    assert path.name == "python"
    assert path.parent.name == "bin"
    assert path.parent.parent.name in {".venv-email", ".venv"}


def test_fcc_wrapper_forces_loopback_after_env_loading():
    wrapper = (ROOT / "scripts" / "fcc-server-wrapper.sh").read_text()
    last_env_load = wrapper.index('load_env_file "$ROOT/.env.fcc"')
    forced_host = wrapper.index("export HOST=127.0.0.1")
    assert forced_host > last_env_load
    assert 'export PORT="${MM_FCC_PORT:-8082}"' in wrapper
