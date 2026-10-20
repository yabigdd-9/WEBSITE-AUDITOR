"""Standalone/runner contention and verified descriptor handoff on real file locks."""

import importlib.util
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from ops.hermes_zero_token import worker_ownership as ownership

ROOT = Path(__file__).resolve().parents[2]


def clean_environment():
    return {key: value for key, value in os.environ.items()
            if key in {"PATH", "HOME", "TMPDIR", "LANG", "LC_ALL"}}


def contender(directory, *, env=None, pass_fds=()):
    program = (
        "import sys;sys.path.insert(0,sys.argv[1]);"
        "from ops.hermes_zero_token.worker_ownership import worker_lock;"
        "\ntry:\n with worker_lock(sys.argv[2],'staging_db'): pass"
        "\nexcept BlockingIOError: sys.exit(75)"
    )
    return subprocess.run([sys.executable, "-B", "-c", program, str(ROOT), str(directory)],
                          env=env or clean_environment(), pass_fds=pass_fds,
                          capture_output=True, text=True, timeout=5)


@pytest.mark.parametrize("name", sorted(ownership.STAGING_WORKERS))
def test_each_standalone_main_refuses_a_concurrent_runner_owner(tmp_path, monkeypatch, name):
    path = Path(__file__).with_name(name + ".py")
    spec = importlib.util.spec_from_file_location("standalone_" + name, path)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    monkeypatch.setattr(worker, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(worker, "_main", lambda: pytest.fail("duplicate work admitted"))
    monkeypatch.delenv(ownership.FD_ENV, raising=False)
    monkeypatch.delenv(ownership.GROUP_ENV, raising=False)
    directory = tmp_path / "state/hermes_zero_token/locks"
    with ownership.worker_lock(directory, "staging_db"), ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(worker.main).result(timeout=5) == 75
    monkeypatch.setattr(worker, "_main", lambda: 0)
    assert worker.main() == 0


def test_same_worker_nesting_is_reentrant_but_other_staging_jobs_are_not(tmp_path):
    with ownership.worker_lock(tmp_path, "staging_db") as outer:
        with ownership.worker_lock(tmp_path, "staging_db") as inner:
            assert inner.descriptor == outer.descriptor
        with pytest.raises(BlockingIOError), ownership.worker_lock(tmp_path, "outreach_draft"):
            pytest.fail("different job used a reentrancy exemption")


def test_real_child_handoff_cannot_unlock_parent_on_exit(tmp_path):
    with ownership.worker_lock(tmp_path, "staging_db") as lease:
        env = {**clean_environment(), **{
            ownership.FD_ENV: str(lease.descriptor), ownership.GROUP_ENV: lease.group}}
        assert contender(tmp_path, env=env, pass_fds=(lease.descriptor,)).returncode == 0
        assert contender(tmp_path).returncode == 75
    assert contender(tmp_path).returncode == 0


def test_unlocked_unrelated_fd_cannot_bypass_an_existing_owner(tmp_path):
    unrelated = tmp_path / "unrelated"
    unrelated.write_text("retain this content")
    with unrelated.open() as handle, ownership.worker_lock(tmp_path, "staging_db"):
        env = {**clean_environment(), ownership.FD_ENV: str(handle.fileno()),
               ownership.GROUP_ENV: "staging-artifacts"}
        result = contender(tmp_path, env=env, pass_fds=(handle.fileno(),))
        assert result.returncode != 0
        assert "OwnershipError" in result.stderr
        assert contender(tmp_path).returncode == 75
    assert unrelated.read_text() == "retain this content"


@pytest.mark.parametrize("value,group", [("999999", "staging-artifacts"),
                                         ("bad", "staging-artifacts"),
                                         ("1", "other-group")])
def test_forged_handoff_is_a_blocked_report(tmp_path, monkeypatch, capsys, value, group):
    monkeypatch.setenv(ownership.FD_ENV, value)
    monkeypatch.setenv(ownership.GROUP_ENV, group)
    assert ownership.run_owned_worker(tmp_path, "staging_db", lambda: pytest.fail("ran")) == 3
    assert json.loads(capsys.readouterr().out)["production_written"] is False


def test_standalone_policy_overrides_hostile_flags_and_honors_stop(tmp_path, monkeypatch):
    for key in ownership.ZERO_TOKEN_ENV:
        monkeypatch.setenv(key, "unsafe")

    def work():
        assert all(os.environ[key] == value for key, value in ownership.ZERO_TOKEN_ENV.items())
        return 0

    assert ownership.run_owned_worker(tmp_path, "staging_db", work) == 0
    monkeypatch.setenv("HERMES_ZERO_TOKEN_DISABLE_ALL", "1")
    assert ownership.run_owned_worker(tmp_path, "staging_db", lambda: pytest.fail("ran")) == 3


def test_symlink_and_hardlink_lockfiles_are_refused_without_changes(tmp_path):
    other = tmp_path / "other"
    other.write_text("preserve")
    lock = tmp_path / "staging-artifacts.lock"
    lock.symlink_to(other)
    with pytest.raises(OSError), ownership.worker_lock(tmp_path, "staging_db"):
        pytest.fail("symlink followed")
    lock.unlink()
    os.link(other, lock)
    with pytest.raises(ownership.OwnershipError), ownership.worker_lock(tmp_path, "staging_db"):
        pytest.fail("hardlink followed")
    assert other.read_text() == "preserve"


@pytest.mark.parametrize("worker", ["../escape", "x/y", "", None])
def test_worker_names_cannot_choose_lock_paths(tmp_path, worker):
    with pytest.raises(ownership.OwnershipError), ownership.worker_lock(tmp_path, worker):
        pytest.fail("invalid name admitted")
