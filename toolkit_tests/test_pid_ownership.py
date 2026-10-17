"""Isolated ownership regressions for the actual CLI PID guard."""
import fcntl
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "money-machine/supervisor/pid.py"
spec = importlib.util.spec_from_file_location("isolated_pid", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
PIDFile = module.PIDFile


def test_empty_file_is_locked_before_recovery(tmp_path):
    path = tmp_path / "owner.pid"
    path.touch()
    owner = PIDFile(path)
    assert owner.acquire()
    inode = path.stat().st_ino
    try:
        competitor = PIDFile(path)
        assert not competitor.acquire()
        competitor.release()
        assert path.read_text() == str(os.getpid())
    finally:
        owner.release()
    assert path.exists() and path.read_text() == ""
    assert path.stat().st_ino == inode
    assert competitor.acquire()
    competitor.release()


def test_permission_error_cannot_recover_legacy_owner(tmp_path):
    path = tmp_path / "owner.pid"
    path.write_text("43210")
    owner = PIDFile(path)
    with patch.object(module.os, "kill", side_effect=PermissionError):
        assert not owner.acquire()
    assert path.read_text() == "43210"
    owner.release()
    assert path.read_text() == "43210"


def test_dead_and_malformed_legacy_owners_recover(tmp_path):
    for value in ("43210", "bad", "", "-1"):
        path = tmp_path / "owner.pid"
        path.write_text(value)
        owner = PIDFile(path)
        with patch.object(module.os, "kill", side_effect=ProcessLookupError):
            assert owner.acquire()
        owner.release()


def test_release_never_unlinks_replacement(tmp_path):
    path = tmp_path / "owner.pid"
    owner = PIDFile(path)
    assert owner.acquire()
    path.rename(tmp_path / "old-inode")
    path.write_text("replacement")
    owner.release()
    assert path.read_text() == "replacement"


def test_owned_child_excludes_other_process(tmp_path):
    path = tmp_path / "owner.pid"
    code = """import fcntl
import importlib.util, sys
s = importlib.util.spec_from_file_location('pid', sys.argv[1])
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
p = m.PIDFile(sys.argv[2]); print(p.acquire(), flush=True)
sys.stdin.readline(); p.release()
"""
    child = subprocess.Popen([sys.executable, "-B", "-c", code, str(SOURCE), str(path)],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "True"
        assert not PIDFile(path).acquire()
    finally:
        child.communicate("stop\n", timeout=10)
    assert child.returncode == 0
    owner = PIDFile(path)
    assert owner.acquire()
    owner.release()


def test_empty_file_held_before_pid_write_cannot_be_replaced(tmp_path):
    path = tmp_path / "owner.pid"
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        inode = path.stat().st_ino
        competitor = PIDFile(path)
        assert not competitor.acquire()
        competitor.release()
        assert path.stat().st_ino == inode
        assert path.read_text() == ""
    finally:
        os.close(fd)
