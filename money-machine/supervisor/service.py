#!/usr/bin/env python3
"""Restart-safe supervisor for the deterministic MoneyMachine pipeline."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

MM_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = MM_DIR.parent
if str(MM_DIR) not in sys.path:
    sys.path.insert(0, str(MM_DIR))

from supervisor.daemon import LOG_DIR, PIDFILE, SupervisorDaemon, _pid_is_alive, rotate_logs

STATE_DIR = REPO_ROOT / "state"
EVENT_LOG = STATE_DIR / "supervisor-events.jsonl"
CHILD_LOG = STATE_DIR / "worker-logs" / "pipeline-supervised.log"


def _event(kind: str, **fields):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"kind": kind, "at": time.time(), **fields}
    with open(EVENT_LOG, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def status() -> dict:
    probe = SupervisorDaemon()
    result = probe.status()
    result.update(
        event_log=str(EVENT_LOG),
        child_log=str(CHILD_LOG),
        external_send_disabled=True,
    )
    return result


def _pipeline_command(args) -> list[str]:
    command = [
        sys.executable,
        str(MM_DIR / "mm_operator.py"),
        "run-pipeline",
        "--daemon",
        "--sleep",
        str(args.sleep),
        "--report-every",
        str(args.report_every),
        "--lease",
        str(args.lease),
    ]
    for worker in args.worker or []:
        command.extend(["--worker", worker])
    return command


def run_foreground(args) -> int:
    daemon = SupervisorDaemon()
    if not daemon.start():
        current = daemon.status()
        print(json.dumps({"started": False, "reason": "already_running", **current}, indent=2))
        return 2

    env = os.environ.copy()
    env["MM_EXTERNAL_SEND_DISABLED"] = "1"
    env.pop("LIVE_SEND_ENABLED", None)
    CHILD_LOG.parent.mkdir(parents=True, exist_ok=True)
    rotate_logs()

    backoff = 2.0
    child = None
    try:
        while daemon.running:
            command = _pipeline_command(args)
            with open(CHILD_LOG, "a", encoding="utf-8") as log_handle:
                child = subprocess.Popen(
                    command,
                    cwd=REPO_ROOT,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    env=env,
                    start_new_session=False,
                )
            _event("child_started", child_pid=child.pid, command=command)
            daemon.tick({"child_pid": child.pid, "restart_backoff_seconds": backoff})

            while daemon.running and child.poll() is None:
                daemon.tick({"child_pid": child.pid, "restart_backoff_seconds": backoff})
                rotate_logs()
                time.sleep(max(1.0, args.heartbeat))

            if not daemon.running:
                break

            code = child.returncode
            _event("child_exited", child_pid=child.pid, returncode=code)
            time.sleep(backoff)
            backoff = min(args.max_backoff, backoff * 2)
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        daemon.close()
        _event("supervisor_stopped")
    return 0


def start_background(args) -> dict:
    current = status()
    if current["running"]:
        return {"started": False, "reason": "already_running", **current}

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log_handle = open(STATE_DIR / "supervisor-launch.log", "a", encoding="utf-8")
    env = os.environ.copy()
    env["MM_EXTERNAL_SEND_DISABLED"] = "1"
    env.pop("LIVE_SEND_ENABLED", None)

    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "run",
        "--sleep",
        str(args.sleep),
        "--report-every",
        str(args.report_every),
        "--lease",
        str(args.lease),
        "--heartbeat",
        str(args.heartbeat),
        "--max-backoff",
        str(args.max_backoff),
    ]
    for worker in args.worker or []:
        command.extend(["--worker", worker])

    process = subprocess.Popen(
        command,
        cwd=REPO_ROOT,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        env=env,
        start_new_session=True,
    )
    log_handle.close()

    for _ in range(30):
        time.sleep(0.1)
        current = status()
        if current["running"]:
            return {"started": True, "launcher_pid": process.pid, **current}
        if process.poll() is not None:
            break

    return {
        "started": False,
        "launcher_pid": process.pid,
        "reason": "supervisor_failed_to_start",
        **status(),
    }


def stop() -> dict:
    current = status()
    pid = current.get("pid")
    if not pid or not _pid_is_alive(pid):
        return {"stopped": True, "already_stopped": True, **current}

    os.kill(pid, signal.SIGTERM)
    for _ in range(100):
        if not _pid_is_alive(pid):
            return {"stopped": True, "pid": pid}
        time.sleep(0.1)
    return {"stopped": False, "pid": pid, "reason": "timeout_waiting_for_exit"}


def tail_logs(lines: int = 80) -> dict:
    def tail(path: Path):
        if not path.exists():
            return []
        content = path.read_text(errors="replace").splitlines()
        return content[-lines:]

    return {
        "event_log": str(EVENT_LOG),
        "child_log": str(CHILD_LOG),
        "events": tail(EVENT_LOG),
        "pipeline": tail(CHILD_LOG),
    }


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    for name in ("run", "start"):
        q = sub.add_parser(name)
        q.add_argument("--worker", action="append")
        q.add_argument("--sleep", type=float, default=60)
        q.add_argument("--report-every", type=int, default=10)
        q.add_argument("--lease", type=int, default=300)
        q.add_argument("--heartbeat", type=float, default=5)
        q.add_argument("--max-backoff", type=float, default=60)

    sub.add_parser("status")
    sub.add_parser("stop")
    q = sub.add_parser("logs")
    q.add_argument("--lines", type=int, default=80)
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if args.cmd == "run":
        return run_foreground(args)
    if args.cmd == "start":
        print(json.dumps(start_background(args), indent=2))
        return 0
    if args.cmd == "status":
        print(json.dumps(status(), indent=2))
        return 0
    if args.cmd == "stop":
        result = stop()
        print(json.dumps(result, indent=2))
        return 0 if result.get("stopped") else 2
    if args.cmd == "logs":
        print(json.dumps(tail_logs(args.lines), indent=2))
        return 0
    raise AssertionError(args.cmd)


if __name__ == "__main__":
    raise SystemExit(main())
