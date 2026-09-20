import importlib.util
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_full_pipeline_email_discovery_accepts_none_state(tmp_path):
    mod = load(ROOT / "full-pipeline.py", "full_pipeline_test")
    mod.AUDITS = tmp_path / "audits"
    mod.AUDITS.mkdir()
    mod.CFG = {
        "quiet": True,
        "delay": 0,
        "output_dir": str(tmp_path),
        "max_workers": 1,
    }
    results, errors = mod.run_email_discovery(max_workers=1, state=None)
    assert results == {}
    assert errors == {}


def test_supervisor_pid_probe_and_start(tmp_path):
    daemon = load(ROOT / "money-machine" / "supervisor" / "daemon.py", "supervisor_test")

    assert daemon._pid_is_alive(os.getpid())
    assert not daemon._pid_is_alive(-1)

    pidfile = tmp_path / "state" / "supervisor.pid"
    heartbeat = tmp_path / "state" / "supervisor.heartbeat"
    supervisor = daemon.SupervisorDaemon(pidfile=pidfile, heartbeat=heartbeat)

    assert supervisor.start() is True
    assert pidfile.read_text().strip() == str(os.getpid())
    tick = supervisor.tick()
    assert tick["running"] is True
    assert heartbeat.exists()


def test_supervisor_blocks_live_duplicate(tmp_path):
    daemon = load(ROOT / "money-machine" / "supervisor" / "daemon.py", "supervisor_duplicate_test")
    pidfile = tmp_path / "supervisor.pid"
    heartbeat = tmp_path / "supervisor.heartbeat"
    pidfile.write_text(str(os.getpid()))

    supervisor = daemon.SupervisorDaemon(pidfile=pidfile, heartbeat=heartbeat)
    assert supervisor.start() is False


def test_log_rotation_handles_missing_dir(tmp_path):
    daemon = load(ROOT / "money-machine" / "supervisor" / "daemon.py", "supervisor_rotation_test")
    assert daemon.rotate_logs(tmp_path / "missing") == []
