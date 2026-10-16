"""Isolated regression tests for SupervisorDaemon.start() PID-lock logic.

Covers the commit 5f461d43 regression where os.kill(pid, 0) handling was inverted:
  * live PID       -> start() returns False (block duplicate startup)
  * dead PID       -> start() recovers stale ownership and returns True
  * PermissionError -> start() fails closed and returns False
  * malformed PID  -> start() recovers stale ownership and returns True

Isolation: the constructor creates LOG_DIR and installs SIGTERM/SIGINT handlers,
so tests redirect LOG_DIR into tmp_path and restore the original signal handlers
after construction — nothing touches the live repo or process signal state.
"""
from __future__ import annotations

import os
import signal
from pathlib import Path
import sys

import pytest

MM = Path(__file__).resolve().parent.parent / "money-machine"
if str(MM) not in sys.path:
    sys.path.insert(0, str(MM))

import supervisor.daemon as daemon_mod
from supervisor.daemon import SupervisorDaemon


@pytest.fixture
def isolated_daemon(tmp_path, monkeypatch):
    """Build SupervisorDaemon without touching the live repo or signal state.

    Redirects LOG_DIR into tmp_path (constructor's mkdir) and restores the
    original SIGTERM/SIGINT handlers after construction.
    """
    original_handlers = {
        sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)
    }
    log_dir = tmp_path / "worker-logs"
    monkeypatch.setattr(daemon_mod, "LOG_DIR", log_dir)

    def build(pid_content: str | None = None) -> SupervisorDaemon:
        pidfile = tmp_path / "supervisor.pid"
        heartbeat = tmp_path / "supervisor.heartbeat"
        if pid_content is not None:
            pidfile.write_text(pid_content)
        return SupervisorDaemon(pidfile=pidfile, heartbeat=heartbeat)

    yield build

    for sig, handler in original_handlers.items():
        try:
            signal.signal(sig, handler)
        except (OSError, ValueError):
            pass


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


def test_start_blocks_when_pidfile_live_pid(isolated_daemon, monkeypatch):
    _install_kill(monkeypatch, "alive")
    assert isolated_daemon(pid_content="12345").start() is False


def test_start_recovers_when_pidfile_dead_pid(isolated_daemon, monkeypatch):
    _install_kill(monkeypatch, "dead")
    d = isolated_daemon(pid_content="12345")
    assert d.start() is True
    # stale ownership recovered: pidfile now holds our own pid
    assert int(d.pidfile.read_text().strip()) == os.getpid()


def test_start_fails_closed_on_permission_error(isolated_daemon, monkeypatch):
    _install_kill(monkeypatch, "permission")
    d = isolated_daemon(pid_content="12345")
    assert d.start() is False
    # fail-closed: pidfile must NOT be overwritten with our pid
    assert d.pidfile.read_text().strip() == "12345"


def test_start_recovers_when_pidfile_malformed(isolated_daemon, monkeypatch):
    _install_kill(monkeypatch, "alive")  # never reached for malformed content
    d = isolated_daemon(pid_content="not-a-pid")
    assert d.start() is True
    assert int(d.pidfile.read_text().strip()) == os.getpid()


def test_start_succeeds_when_no_pidfile(isolated_daemon, monkeypatch):
    _install_kill(monkeypatch, "alive")
    d = isolated_daemon()  # no pidfile
    assert d.start() is True
    assert int(d.pidfile.read_text().strip()) == os.getpid()


def test_start_kill_receives_signal_zero(isolated_daemon, monkeypatch):
    seen = {}

    def fake_kill(target: int, sig: int) -> None:
        seen["sig"] = sig

    monkeypatch.setattr(os, "kill", fake_kill)
    d = isolated_daemon(pid_content="42")
    d.start()
    assert seen["sig"] == 0


def test_start_signal_handlers_restored(isolated_daemon, monkeypatch):
    """Constructor-installed handlers must not leak into the process."""
    _install_kill(monkeypatch, "alive")
    isolated_daemon().start()
    for sig in (signal.SIGTERM, signal.SIGINT):
        assert signal.getsignal(sig) is not SupervisorDaemon._on_stop  # not _on_stop
