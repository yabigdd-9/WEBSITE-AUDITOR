"""P3 control-plane tests: supervisor start/stop/status/leases/crash recovery.

Runs the supervisor CLI in isolated temp workspaces (MM_ROOT=<tmpdir>) via the
`mm` operator so tests never touch the live database. Exercises:

  * supervisor status/health/logs on a fresh workspace
  * single-instance protection (second start blocked)
  * graceful stop via SIGTERM
  * crash recovery: a durable queued item survives supervisor death and is
    reclaimed on restart with no duplicate side effects
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
MM = REPO / "money-machine" / "mm_operator.py"
PY = sys.executable


def run_mm(mm_root: Path, *argv: str, timeout: int = 60) -> subprocess.CompletedProcess:
    env = dict(os.environ, MM_ROOT=str(mm_root))
    return subprocess.run([PY, str(MM), *argv], capture_output=True, text=True,
                          timeout=timeout, env=env, cwd=str(REPO))


def mm_json(mm_root: Path, *argv: str, timeout: int = 60) -> dict:
    proc = run_mm(mm_root, *argv, timeout=timeout)
    assert proc.returncode == 0, f"mm {' '.join(argv)} failed: {proc.stderr[-2000:]}"
    return json.loads(proc.stdout)


def seed_pipeline(mm_root: Path, business_id: int = 9001, state: str = "DISCOVERED") -> None:
    db = mm_root / "database" / "money_machine.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    d = sqlite3.connect(db)
    d.execute("CREATE TABLE IF NOT EXISTS businesses("
              "id INTEGER PRIMARY KEY, name TEXT, region TEXT, public_website TEXT,"
              "source TEXT, discovered_at TEXT, current_status TEXT, is_dummy INTEGER)")
    d.execute("INSERT OR IGNORE INTO businesses VALUES(?,?,?,?,?,?,?,?)",
              (business_id, f"Test Biz {business_id}", "Test",
               "https://test-biz.example.co.nz", "test", "2026-01-01T00:00:00+00:00",
               "discovered", 0))
    d.execute("CREATE TABLE IF NOT EXISTS mm_deals(business_id INTEGER PRIMARY KEY,"
              "stage TEXT, updated_at TEXT)")
    d.execute("INSERT OR IGNORE INTO mm_deals VALUES(?, 'DISCOVERED', ?)",
              (business_id, "2026-01-01T00:00:00+00:00"))
    d.commit()
    d.close()
    res = mm_json(mm_root, "pipeline-enqueue", str(business_id), "--state", state)
    assert res["business_id"] == business_id


def item_state(mm_root: Path, business_id: int) -> dict:
    db = mm_root / "database" / "money_machine.db"
    d = sqlite3.connect(db)
    d.row_factory = sqlite3.Row
    row = d.execute("SELECT * FROM pipeline_items WHERE business_id=?",
                    (business_id,)).fetchone()
    d.close()
    return dict(row) if row else {}


def test_supervisor_status_health_logs_on_fresh_workspace(tmp_path):
    root = tmp_path / "ws"
    status = mm_json(root, "supervisor", "status")
    assert status["running"] is False
    assert status["pid"] is None
    health = mm_json(root, "supervisor", "health")
    assert health["supervisor"]["running"] is False
    assert health["pipeline"]["initialised"] is False  # no tables yet, no write
    logs = mm_json(root, "supervisor", "logs", "--tail", "5")
    assert logs["log_dir"].endswith("worker-logs")
    assert logs["files"] == {}


def test_supervisor_start_stop_lifecycle(tmp_path):
    root = tmp_path / "ws"
    started = mm_json(root, "supervisor", "start", "--sleep", "1")
    assert started["started"] is True
    assert started["pid"]
    try:
        status = mm_json(root, "supervisor", "status")
        assert status["running"] is True
        assert status["pid"] == started["pid"]
        heartbeat = status["heartbeat"]
        # A healthy supervisor may deliberately pause work when the runtime
        # disk guard is active; it is still alive and must remain controllable.
        assert heartbeat and heartbeat["status"] in {"running", "paused_low_disk"}
        # single-instance protection: second start must be refused
        again = mm_json(root, "supervisor", "start")
        assert again["started"] is False
        assert again["reason"] == "already_running"
        assert again["pid"] == started["pid"]
    finally:
        stopped = mm_json(root, "supervisor", "stop", "--timeout", "15")
    assert stopped["stopped"] is True
    assert stopped["pid"] == started["pid"]
    assert mm_json(root, "supervisor", "status")["running"] is False


def test_supervisor_stop_when_not_running(tmp_path):
    root = tmp_path / "ws"
    res = mm_json(root, "supervisor", "stop")
    assert res == {"stopped": False, "reason": "not_running"}


@pytest.mark.slow
def test_supervisor_crash_recovery_no_duplicate_work(tmp_path):
    """SIGKILL the supervisor mid-run; a queued item must survive in durable
    state and be reclaimed by a restart, with no duplicate item rows and no
    duplicate audit events per business/state edge."""
    import signal as _signal
    root = tmp_path / "ws"
    bid = 9001
    seed_pipeline(root, bid)
    assert item_state(root, bid)["state"] == "DISCOVERED"

    started = mm_json(root, "supervisor", "start", "--sleep", "1")
    assert started["started"] is True
    time.sleep(2)  # let the loop claim/process at least one cycle
    os.kill(started["pid"], _signal.SIGKILL)  # no graceful shutdown
    time.sleep(1)

    after_kill = item_state(root, bid)
    assert after_kill, "queued item must survive a supervisor crash"
    assert after_kill["lease_owner"] is None  # no orphaned lease may persist

    restarted = mm_json(root, "supervisor", "start", "--sleep", "1")
    try:
        assert restarted["started"] is True
        time.sleep(3)  # stale leases drain; workers resume from durable state
        final = item_state(root, bid)
        assert final, "item must still exist after restart"
        db = root / "database" / "money_machine.db"
        d = sqlite3.connect(db)
        try:
            n_items = d.execute(
                "SELECT count(*) FROM pipeline_items WHERE business_id=?", (bid,)).fetchone()[0]
            events = d.execute(
                "SELECT from_state, to_state, actor, reason FROM pipeline_events "
                "WHERE business_id=? ORDER BY rowid", (bid,)).fetchall()
        finally:
            d.close()
        assert n_items == 1, "restart must not duplicate the queued item"
        edges = [(r[0], r[1]) for r in events]
        # no duplicated transition edges (idempotent resume, no double-advance)
        assert len(edges) == len(set(edges)), f"duplicate transition edges: {edges}"
    finally:
        mm_json(root, "supervisor", "stop", "--timeout", "15")
