import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MM = ROOT / "money-machine"
if str(MM) not in sys.path:
    sys.path.insert(0, str(MM))

spec = importlib.util.spec_from_file_location("mm_runtime_guards_under_test", MM / "mm_runtime_guards.py")
guards = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(guards)


def test_disk_guard_pauses_when_below_threshold(tmp_path):
    fake = type("Usage", (), {"free": 100 * 1024 * 1024})()
    with patch.object(guards.shutil, "disk_usage", return_value=fake):
        result = guards.disk_guard(tmp_path, min_free_mb=1024)
    assert result["ok"] is False
    assert result["action"] == "pause_new_work"


def test_disk_guard_allows_when_space_is_sufficient(tmp_path):
    fake = type("Usage", (), {"free": 2048 * 1024 * 1024})()
    with patch.object(guards.shutil, "disk_usage", return_value=fake):
        result = guards.disk_guard(tmp_path, min_free_mb=1024)
    assert result["ok"] is True
    assert result["action"] == "continue"


def test_network_guard_degrades_without_blocking_local_work():
    def fail(*args, **kwargs):
        raise OSError("offline fixture")
    result = guards.network_guard(resolver=fail)
    assert result["ok"] is False
    assert "local work may continue" in result["action"]


def test_snapshot_can_skip_network_probe(tmp_path, monkeypatch):
    monkeypatch.setenv("MM_ROOT", str(tmp_path))
    fake = type("Usage", (), {"free": 2048 * 1024 * 1024})()
    with patch.object(guards.shutil, "disk_usage", return_value=fake):
        result = guards.snapshot(probe_network=False)
    assert result["disk"]["ok"] is True
    assert result["network"]["ok"] is None
    assert result["paid_calls"] == 0
    assert result["external_sends"] == 0
