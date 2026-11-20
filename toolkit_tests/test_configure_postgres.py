"""Secret handling and activation boundaries; no real credentials or sends."""

import getpass
import subprocess
import warnings
from unittest.mock import Mock

import pytest

from scripts import configure_postgres as setup

SYNTHETIC_SECRET = "synthetic-private-connection-value"


@pytest.fixture
def private_terminal(monkeypatch):
    monkeypatch.setattr(setup.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(setup.getpass, "getpass", lambda _: SYNTHETIC_SECRET)
    store = Mock()
    store.read.return_value = {"schema_version": 1, "prospects": {}, "events": []}
    factory = Mock(return_value=store)
    monkeypatch.setattr(setup, "PostgresPipelineStore", factory)
    transport = Mock()
    monkeypatch.setattr(setup.subprocess, "run", transport)
    return store, factory, transport


def test_default_only_checks_database_and_never_mutates(private_terminal, capsys):
    store, factory, transport = private_terminal
    assert setup.main([]) == 0
    factory.assert_called_once_with(SYNTHETIC_SECRET)
    store.read.assert_called_once_with()
    store.operational_summary.assert_called_once_with()
    store.transaction.assert_not_called()
    transport.assert_not_called()
    assert SYNTHETIC_SECRET not in capsys.readouterr().out


def test_secret_install_uses_stdin_only_after_database_checks(private_terminal, capsys):
    store, _, transport = private_terminal
    order = []
    store.read.side_effect = lambda: order.append("database") or {"schema_version": 1}
    store.operational_summary.side_effect = lambda: order.append("ledger") or {}

    def run(arguments, **kwargs):
        if "secret" in arguments:
            order.append("install")
            assert kwargs["input"] == SYNTHETIC_SECRET
            assert SYNTHETIC_SECRET not in arguments
            assert arguments == ["gh", "secret", "set", "WA_POSTGRES_DSN", "--repo", setup.REPOSITORY]
        else:
            order.append("authentication")
            assert kwargs["input"] is None
            assert arguments == ["gh", "auth", "status", "--hostname", "github.com"]
        assert kwargs["capture_output"] is True
        assert kwargs["check"] is True
        assert kwargs["timeout"] == 30

    transport.side_effect = run
    assert setup.main(["--install-github-secret"]) == 0
    assert order == ["authentication", "database", "ledger", "install"]
    store.transaction.assert_not_called()
    assert SYNTHETIC_SECRET not in capsys.readouterr().out


def test_noninteractive_execution_never_prompts_or_calls_provider(private_terminal, monkeypatch):
    _, factory, transport = private_terminal
    monkeypatch.setattr(setup.sys.stdin, "isatty", lambda: False)
    prompt = Mock(side_effect=AssertionError("A non-TTY must not read a secret"))
    monkeypatch.setattr(setup.getpass, "getpass", prompt)
    assert setup.main(["--install-github-secret"]) == 2
    prompt.assert_not_called()
    factory.assert_not_called()
    transport.assert_not_called()


def test_echoing_fallback_is_rejected_before_reading_secret(private_terminal, monkeypatch):
    _, factory, transport = private_terminal

    def echo_unavailable(_):
        warnings.warn("Cannot control terminal echo", getpass.GetPassWarning)
        pytest.fail("getpass echoing fallback reached")

    monkeypatch.setattr(setup.getpass, "getpass", echo_unavailable)
    assert setup.main([]) == 2
    factory.assert_not_called()
    transport.assert_not_called()


@pytest.mark.parametrize("stage", ["authentication", "connection", "uninitialized", "ledger", "install"])
def test_failures_are_redacted_and_do_not_bypass_verification(private_terminal, stage, capsys):
    store, factory, transport = private_terminal
    secret_error = RuntimeError(SYNTHETIC_SECRET)
    if stage == "authentication":
        transport.side_effect = secret_error
    elif stage == "connection":
        factory.side_effect = secret_error
    elif stage == "uninitialized":
        store.read.return_value = None
    elif stage == "ledger":
        store.operational_summary.side_effect = secret_error
    else:
        transport.side_effect = [None, subprocess.CalledProcessError(1, ["gh"], stderr=SYNTHETIC_SECRET)]
    assert setup.main(["--install-github-secret"]) == 2
    output = capsys.readouterr()
    assert SYNTHETIC_SECRET not in output.out
    assert SYNTHETIC_SECRET not in output.err
    assert "blocked" in output.out
    if stage != "install":
        assert not any("secret" in call.args[0] for call in transport.call_args_list)
    store.transaction.assert_not_called()


def test_empty_input_does_not_fall_back_to_an_environment_credential(private_terminal, monkeypatch):
    _, factory, transport = private_terminal
    monkeypatch.setattr(setup.getpass, "getpass", lambda _: "")
    monkeypatch.setenv("WA_POSTGRES_DSN", SYNTHETIC_SECRET)
    assert setup.main([]) == 2
    factory.assert_not_called()
    transport.assert_not_called()


def test_rejected_arguments_do_not_echo_accidentally_supplied_secrets(private_terminal, capsys):
    _, factory, transport = private_terminal
    with pytest.raises(SystemExit) as result:
        setup.main(["--dsn", SYNTHETIC_SECRET])
    assert result.value.code == 2
    output = capsys.readouterr()
    assert SYNTHETIC_SECRET not in output.out
    assert SYNTHETIC_SECRET not in output.err
    factory.assert_not_called()
    transport.assert_not_called()
