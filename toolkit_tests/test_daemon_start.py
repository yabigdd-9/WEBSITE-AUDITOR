"""Isolated regression tests for SupervisorDaemon.start() PID-lock logic.

Covers the commit 5f461d43 regression where os.kill(pid, 0) handling was inverted:
  * live PID       -> start() returns False (block duplicate startup)
  * dead PID       -> start() recovers stale ownership and returns True
  * PermissionError -> start() fails closed and returns False
  * malformed PID  -> start() recovers stale ownership and returns True
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest

MM = Path(__file__).resolve().parent.parent / "money-machine"
if str(MM) not in sys.path:
    sys.path.insert(0, str(MM))

from supervisor.daemon import SupervisorDaemon


def _daemon(tmp_path: Path, pid_content: str | None = None) -> SupervisorDaemon:
    pidfile = tmp_path / "supervisor.pid"
    heartbeat = tmp_path / "supervisor.heartbeat"
    if pid_content is not None:
        pidfile.write_text(pid_content)
    return SupervisorDaemon(pidfile=pidfile, heartbeat=heartbeat)


def _install_kill(monkeypatch, mode: str) -> None:
    """Replace os.kill so os.kill(pid, 0) behaves as requested."""
    def fake_kill(target: int, sig: int) -> None:
        assert sig == 0, f"unexpected signal {sig}"
        if mode == "alive":
            return  # process exists
        if mode == "dead":
            raise ProcessLookupError("no such process")
        if mode == "permission":
            raise PermissionError("operation not permitted")
        raise AssertionError(f"unexpected mode {mode}")

    monkeypatch.setattr(os, "kill", fake_kill)


def test_start_blocks_when_pidfile_live_pid(tmp_path, monkeypatch):
    _install_kill(monkeypatch, "alive")
    d = _daemon(tmp_path, pid_content="12345")
    assert d.start() is False


def test_start_recovers_when_pidfile_dead_pid(tmp_path, monkeypatch):
    _install_kill(monkeypatch, "dead")
    d = _daemon(tmp_path, pid_content="12345")
    assert d.start() is True
    # stale ownership recovered: pidfile now holds our own pid
    assert int(d.pidfile.read_text().strip()) == os.getpid()


def test_start_fails_closed_on_permission_error(tmp_path, monkeypatch):
    _install_kill(monkeypatch, "permission")
    d = _daemon(tmp_path, pid_content="12345")
    assert d.start() is False
    # fail-closed: pidfile must NOT be overwritten with our pid
    assert d.pidfile.read_text().strip() == "12345"


def test_start_recovers_when_pidfile_malformed(tmp_path, monkeypatch):
    _install_kill(monkeypatch, "alive")  # never reached for malformed content
    d = _daemon(tmp_path, pid_content="not-a-pid")
    assert d.start() is True
    assert int(d.pidfile.read_text().strip()) == os.getpid()


def test_start_succeeds_when_no_pidfile(tmp_path, monkeypatch):
    _install_kill(monkeypatch, "alive")
    d = _daemon(tmp_path)  # no pidfile
    assert d.start() is True
    assert int(d.pidfile.read_text().strip()) == os.getpid()


def test_start_kill_receives_signal_zero(tmp_path, monkeypatch):
    seen = {}

    def fake_kill(target: int, sig: int) -> None:
        seen["sig"] = sig

    monkeypatch.setattr(os, "kill", fake_kill)
    d = _daemon(tmp_path, pid_content="42")
    d.start()
    assert seen["sig"] == 0
