"""Liveness must allow restart after death without replacing a live worker."""

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "supervisor_pid_under_test",
    Path(__file__).resolve().parents[1] / "money-machine/supervisor/pid.py",
)
pid_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pid_module)


@pytest.mark.parametrize("state,alive", [("R", True), ("S", True), ("Z", False), ("X", False)])
def test_linux_process_state_handles_parentheses_in_name(monkeypatch, state, alive):
    monkeypatch.setattr(pid_module.os, "kill", lambda *_: None)
    monkeypatch.setattr(Path, "read_text", lambda *_: f"123 (worker (audit) queue) {state} 1 0")
    assert pid_module.is_process_alive(123) is alive


@pytest.mark.parametrize("pid", [0, -1])
def test_nonpositive_pid_never_probes_a_process_group(monkeypatch, pid):
    def forbidden(*_):
        pytest.fail("Must not signal process groups")
    monkeypatch.setattr(pid_module.os, "kill", forbidden)
    assert not pid_module.is_process_alive(pid)


@pytest.mark.parametrize("error,alive", [(ProcessLookupError(), False), (PermissionError(), True)])
def test_missing_and_inaccessible_processes_are_distinct(monkeypatch, error, alive):
    def fail(*_):
        raise error
    monkeypatch.setattr(pid_module.os, "kill", fail)
    assert pid_module.is_process_alive(123) is alive


def test_non_linux_fallback_preserves_live_pid(monkeypatch):
    monkeypatch.setattr(pid_module.os, "kill", lambda *_: None)
    def unavailable(*_):
        raise FileNotFoundError
    monkeypatch.setattr(Path, "read_text", unavailable)
    assert pid_module.is_process_alive(123)
