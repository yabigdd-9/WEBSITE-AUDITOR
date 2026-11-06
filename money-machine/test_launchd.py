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
    assert path.name.startswith("python")
    assert path.parent.name == "bin"
    top = path.parent.parent
    names = {top.name, top.parent.name if top.parent.name else ""}
    assert ".venv-email" in names or ".venv" in names or top.name.startswith("cpython-3.11")


def test_money_machine_python_path_preserves_venv_entrypoint(monkeypatch):
    monkeypatch.delenv("MM_PYTHON", raising=False)
    preferred = ROOT / ".venv-email" / "bin" / "python"
    fallback = ROOT / ".venv" / "bin" / "python"
    expected = preferred if preferred.is_file() else fallback

    assert launchd.python_path() == expected


def test_configured_python_path_does_not_resolve_symlink(monkeypatch):
    candidate = ROOT / ".venv-email" / "bin" / "python"
    monkeypatch.setenv("MM_PYTHON", str(candidate))

    assert launchd.python_path() == candidate


def test_fcc_wrapper_forces_loopback_after_env_loading():
    wrapper = (ROOT / "scripts" / "fcc-server-wrapper.sh").read_text()
    last_env_load = wrapper.index('load_env_file "$ROOT/.env.fcc"')
    forced_host = wrapper.index("export HOST=127.0.0.1")
    assert forced_host > last_env_load
    assert 'export PORT="${MM_FCC_PORT:-8082}"' in wrapper


SEARXNG_MODULE_PATH = ROOT / "money-machine" / "supervisor" / "searxng_launchd.py"
SEARXNG_SPEC = importlib.util.spec_from_file_location(
    "searxng_launchd_under_test", SEARXNG_MODULE_PATH
)
searxng_launchd = importlib.util.module_from_spec(SEARXNG_SPEC)
SEARXNG_SPEC.loader.exec_module(searxng_launchd)


def test_searxng_launchd_is_user_scoped_keepalive_and_isolated():
    payload = searxng_launchd.plist_payload()
    assert payload["RunAtLoad"] is True
    assert payload["KeepAlive"] is True
    assert payload["ProcessType"] == "Background"
    assert payload["ThrottleInterval"] == 10
    assert payload["ProgramArguments"] == [
        str(Path.home() / ".local" / "share" / "searxng" / ".venv" / "bin" / "python"),
        "-m",
        "searx.webapp",
    ]
    env = payload["EnvironmentVariables"]
    assert env["SEARXNG_SETTINGS_PATH"] == str(Path.home() / ".searxng" / "settings.yml")
    assert "MM_ROOT" not in env
    assert not any("OUTREACH" in key or "TOKEN" in key for key in env)
    assert searxng_launchd.LABEL == "ai.website-auditor.searxng"
    assert "Library/LaunchAgents" in str(searxng_launchd.PLIST_PATH)


def test_searxng_wrapper_creates_loopback_json_only_private_service():
    wrapper = (ROOT / "money-machine" / "scripts" / "searxng.sh").read_text()
    assert 'bind_address: "127.0.0.1"' in wrapper
    assert "port: 8888" in wrapper
    assert "- json" in wrapper
    assert "public_instance: false" in wrapper
    assert "chmod 600" in wrapper
    assert '--editable "$SRC"' in wrapper
    assert '--no-build-isolation' in wrapper
    assert r"0\.0\.0\.0:8888" in wrapper  # explicit unsafe-listener rejection
    assert r"\*:8888" in wrapper
    assert "validate_settings()" in wrapper
    assert "BLOCKED_SETTINGS: bind_address must be explicit loopback" in wrapper
    assert "BLOCKED_SETTINGS: public_instance must be false" in wrapper
    assert "BLOCKED_SETTINGS: search.formats must include json" in wrapper
    install_block = wrapper.split("  install)", 1)[1].split("  status)", 1)[0]
    assert install_block.index("ensure_settings") < install_block.index("validate_settings")
    assert install_block.index("validate_settings") < install_block.index('\"$PY\" \"$LAUNCHD\" install')
    assert 'sh "$0" verify' in install_block
    restart_block = wrapper.split("  start|restart)", 1)[1].split("  stop)", 1)[0]
    assert 'sh "$0" verify' in restart_block
