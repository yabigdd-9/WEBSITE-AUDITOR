"""Operator-facing supervisor CLI: start/stop/restart/status/health/logs.

Wires the existing control-plane primitives (SupervisorDaemon PID-lock,
mm_pipeline.run_pipelineloop, mm_workers.WORKERS) behind a single, supervised
entry point so the pipeline can run unattended and survive restarts.

Guarantees:
  * single-instance protection via PID lock + flock
  * graceful SIGTERM/SIGINT shutdown
  * worker heartbeats + stale-lease recovery (handled by mm_pipeline)
  * bounded retries, exponential backoff, dead-letter (handled by mm_pipeline)
  * log rotation (rotate_logs)
  * NO sends/approvals: the outreach worker only advances items to
    APPROVAL_PENDING; the approval/send engine gates everything downstream.

All actions are local and deterministic. No paid model/API usage.
"""
from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from mm_core import connect, now, root
from mm_runtime_guards import (
    disk_guard,
    network_guard_event,
    network_status,
    snapshot as guard_snapshot,
)

STATE = root() / "state"
LOG_DIR = STATE / "worker-logs"
SUPERVISOR_LOG = LOG_DIR / "supervisor.jsonl"
HEARTBEAT = STATE / "supervisor.heartbeat"
LEASE_SECONDS = 300

from supervisor.daemon import rotate_logs  # noqa: E402
from supervisor.pid import PIDFile  # noqa: E402

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _pidfile() -> Path:
    return STATE / "supervisor.pid"


def _read_pid() -> int | None:
    try:
        return int(_pidfile().read_text().strip())
    except Exception:
        return None


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _is_running() -> int | None:
    pid = _read_pid()
    if pid and _pid_alive(pid):
        return pid
    return None


def _log(record: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    record = {"at": now(), **record}
    with open(SUPERVISOR_LOG, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _heartbeat(pid: int, status: str) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    HEARTBEAT.write_text(json.dumps({"pid": pid, "status": status, "at": now()}, default=str))


def _build_workers(names=None, lease_seconds: int = LEASE_SECONDS):
    import mm_pipeline
    import mm_workers
    names = names or list(mm_workers.WORKERS)
    return [
        mm_pipeline.Worker("worker-" + n, *mm_workers.WORKERS[n], lease_seconds=lease_seconds)
        for n in sorted(names)
        if n in mm_workers.WORKERS
    ]


# ---------------------------------------------------------------------------
# subcommands
# ---------------------------------------------------------------------------

def cmd_status(args) -> dict:
    pid = _read_pid()
    alive = pid is not None and _pid_alive(pid)
    try:
        hb = json.loads(HEARTBEAT.read_text())
    except Exception:
        hb = None
    return {
        "running": bool(alive),
        "pid": pid if alive else None,
        "pidfile": str(_pidfile()),
        "heartbeat": hb,
        "state_dir": str(STATE),
    }


def cmd_health(args) -> dict:
    """Read-only health snapshot. Never writes, so it works against a RO handle.

    mm_pipeline.health() calls migrate() (DDL writes), which fails on a
    read-only connection; here we read the pipeline tables directly and only if
    they already exist.
    """
    import datetime as dt
    db_path = root() / "database" / "money_machine.db"
    if not db_path.is_file():
        return {"supervisor": cmd_status(args),
                "pipeline": {"initialised": False, "note": "database not created yet"}}
    with contextlib.closing(connect(readonly=True)) as d:
        try:
            tables = {r[0] for r in d.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if "pipeline_items" not in tables:
                snap = {"initialised": False, "note": "pipeline tables not created yet"}
            else:
                at = dt.datetime.now(dt.timezone.utc).isoformat()
                states = {r[0]: r[1] for r in d.execute(
                    "SELECT state,count(*) FROM pipeline_items GROUP BY state")}
                leased = d.execute(
                    "SELECT count(*) FROM pipeline_items WHERE lease_until IS NOT NULL "
                    "AND lease_until>?", (at,)).fetchone()[0]
                dead = d.execute(
                    "SELECT count(*) FROM pipeline_items WHERE state IN "
                    "('RETRYABLE_FAILURE','PERMANENT_FAILURE')").fetchone()[0]
                snap = {"initialised": True, "states": states,
                        "active_leases": leased, "dead_lettered": dead}
        except Exception as ex:
            snap = {"error": str(ex)}
    return {
        "supervisor": cmd_status(args),
        "pipeline": snap,
        "network": network_status(),
        "guards": guard_snapshot(probe_network=False),
    }


def cmd_logs(args) -> dict:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    tail = int(getattr(args, "tail", 50))
    out = {}
    for f in sorted(LOG_DIR.glob("*.jsonl")):
        try:
            out[f.name] = f.read_text().splitlines()[-tail:]
        except Exception as ex:
            out[f.name] = ["<unreadable: %s>" % ex]
    return {"log_dir": str(LOG_DIR), "files": out}


def _rotate_and_report() -> None:
    try:
        rotate_logs(LOG_DIR)
    except Exception as ex:  # rotation must never crash the loop
        _log({"kind": "logrotate_error", "error": str(ex)})


def cmd_run_foreground(args) -> int:
    """Run the supervisor loop in the foreground (used by start / tests)."""
    import mm_pipeline
    lock = PIDFile(_pidfile())
    if not lock.acquire():
        print("BLOCKED: supervisor already running (pid %s)" % _read_pid(), file=sys.stderr)
        return 2
    stop = {"flag": False}

    def _on_stop(signum, frame):
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _on_stop)
    signal.signal(signal.SIGINT, _on_stop)
    workers = _build_workers(getattr(args, "worker", None), int(getattr(args, "lease", LEASE_SECONDS)))
    sleep_seconds = float(getattr(args, "sleep", 5))
    rotate_every = int(getattr(args, "rotate_every", 60))
    pid = os.getpid()
    _heartbeat(pid, "running")
    _log({"kind": "supervisor_start", "pid": pid, "workers": [w.worker_id for w in workers]})
    cycles = 0
    try:
        db_path = root() / "database" / "money_machine.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.touch(exist_ok=True)  # sqlite needs the file to exist for mode=rw
        with contextlib.closing(connect()) as d, d:
            mm_pipeline.migrate(d)
            while not stop["flag"]:
                disk = disk_guard()
                if not disk["ok"]:
                    cycles += 1
                    _heartbeat(pid, "paused_low_disk")
                    _log({"kind": "runtime_guard", "cycle": cycles, "disk": disk, "action": "pause_new_work"})
                    time.sleep(min(max(sleep_seconds, 1), 60))
                    continue
                snapshot = [{"worker": w.worker_id, "processed": w.run_once(d)} for w in workers]
                mm_pipeline.drain_expired_leases(d)
                d.commit()
                cycles += 1
                _heartbeat(pid, "running")
                _log({"kind": "loop_cycle", "cycle": cycles, "snapshot": snapshot, "disk": disk})
                if cycles % rotate_every == 0:
                    net_result, net_kind = network_guard_event()
                    if net_kind:
                        _log({"kind": net_kind, **net_result})
                    _rotate_and_report()
                for _ in range(int(sleep_seconds * 10)):  # interruptible sleep
                    if stop["flag"]:
                        break
                    time.sleep(0.1)
    finally:
        _heartbeat(pid, "stopped")
        _log({"kind": "supervisor_stop", "pid": pid, "cycles": cycles})
        try:
            lock.release()
        except Exception:
            pass
        _pidfile().unlink(missing_ok=True)
    return 0


def cmd_start(args) -> dict:
    if _is_running():
        return {"started": False, "reason": "already_running", "pid": _read_pid()}
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "supervisor.cli", "_run-foreground",
           "--sleep", str(getattr(args, "sleep", 5)),
           "--lease", str(getattr(args, "lease", LEASE_SECONDS)),
           "--rotate-every", str(getattr(args, "rotate_every", 60))]
    for w in (getattr(args, "worker", None) or []):
        cmd += ["--worker", w]
    mm_pkg = Path(__file__).resolve().parent.parent
    with open(SUPERVISOR_LOG, "a") as logf:
        proc = subprocess.Popen(
            cmd, cwd=str(mm_pkg), stdout=logf,
            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    deadline = time.monotonic() + 5
    started = False
    while time.monotonic() < deadline:
        status = cmd_status(args)
        heartbeat = status["heartbeat"] or {}
        started = (
            status["running"]
            and heartbeat.get("pid") == status["pid"]
            and heartbeat.get("status") in {"running", "paused_low_disk"}
        )
        if started or proc.poll() is not None:
            break
        time.sleep(0.1)
    pid = _read_pid()
    _log({"kind": "supervisor_spawn", "spawn_pid": proc.pid, "supervisor_pid": pid})
    return {"started": bool(started), "pid": pid, "spawn_pid": proc.pid}


def cmd_stop(args) -> dict:
    pid = _is_running()
    if not pid:
        return {"stopped": False, "reason": "not_running"}
    os.kill(pid, signal.SIGTERM)
    deadline = time.time() + float(getattr(args, "timeout", 15))
    while time.time() < deadline:
        if not _pid_alive(pid):
            _pidfile().unlink(missing_ok=True)
            return {"stopped": True, "pid": pid}
        time.sleep(0.1)
    return {"stopped": False, "reason": "timeout", "pid": pid}


def cmd_restart(args) -> dict:
    return {"stop": cmd_stop(args), "start": cmd_start(args)}


def cmd_ensure_running(args) -> dict:
    """Idempotent start-if-dead: no-op when alive, start when dead.

    Designed for cron (`*/5 * * * *` + `@reboot`). Single-instance protection
    comes from the PID lock + flock in _run-foreground, so concurrent invocations
    can never produce duplicate supervisors/workers.
    """
    pid = _is_running()
    if pid:
        return {"ensure_running": True, "started": False,
                "reason": "already_running", "pid": pid}
    start = cmd_start(args)
    return {"ensure_running": True, "recovered": bool(start.get("started")),
            **start}


COMMANDS = {
    "start": cmd_start,
    "stop": cmd_stop,
    "restart": cmd_restart,
    "ensure-running": cmd_ensure_running,
    "status": cmd_status,
    "health": cmd_health,
    "logs": cmd_logs,
}


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=[*COMMANDS, "_run-foreground"])
    p.add_argument("--sleep", type=float, default=5)
    p.add_argument("--tail", type=int, default=50)
    p.add_argument("--timeout", type=float, default=15)
    p.add_argument("--worker", action="append")
    p.add_argument("--lease", type=int, default=LEASE_SECONDS)
    p.add_argument("--rotate-every", type=int, default=60, dest="rotate_every")
    args = p.parse_args(argv)
    if args.action == "_run-foreground":
        return cmd_run_foreground(args)
    print(json.dumps(COMMANDS[args.action](args), indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
