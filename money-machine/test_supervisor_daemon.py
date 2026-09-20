import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "money-machine" / "supervisor" / "daemon.py"
spec = importlib.util.spec_from_file_location("supervisor_under_test", MODULE_PATH)
daemon = importlib.util.module_from_spec(spec)
spec.loader.exec_module(daemon)


def test_pid_liveness():
    assert daemon._pid_is_alive(os.getpid())
    assert not daemon._pid_is_alive(-1)


def test_supervisor_start_tick_stop_and_duplicate(tmp_path, monkeypatch):
    monkeypatch.setattr(daemon, "LOG_DIR", tmp_path / "logs")
    pidfile = tmp_path / "state" / "supervisor.pid"
    heartbeat = tmp_path / "state" / "heartbeat.json"

    supervisor = daemon.SupervisorDaemon(pidfile=pidfile, heartbeat=heartbeat)
    assert supervisor.start() is True
    assert pidfile.exists()
    assert heartbeat.exists()
    assert supervisor.tick()["running"] is True
    assert supervisor.status()["pid"] == os.getpid()

    duplicate = daemon.SupervisorDaemon(pidfile=pidfile, heartbeat=heartbeat)
    assert duplicate.start() is False

    supervisor._on_stop(None, None)
    assert supervisor.running is False
    assert not pidfile.exists()
    assert supervisor.tick() == {"stopped": True}


def test_stale_pid_is_replaced(tmp_path, monkeypatch):
    monkeypatch.setattr(daemon, "LOG_DIR", tmp_path / "logs")
    pidfile = tmp_path / "supervisor.pid"
    heartbeat = tmp_path / "heartbeat.json"
    pidfile.write_text("99999999")

    supervisor = daemon.SupervisorDaemon(pidfile=pidfile, heartbeat=heartbeat)
    assert supervisor.start() is True
    assert int(pidfile.read_text()) == os.getpid()


def test_rotate_logs(tmp_path):
    log = tmp_path / "worker.jsonl"
    log.write_text("x" * 100)
    rotated = daemon.rotate_logs(tmp_path, max_size_mb=0)
    assert len(rotated) == 1
    assert rotated[0].endswith(".gz")
    assert not log.exists()
