"""Auditable, fail-closed runtime soak. Only reads the service database.

The clock starts when this monitor collects its baseline. Every sample survives
interruption; no prior service uptime is credited. A short run can never attest
to 24 hours. Public probes open TCP sockets without sending provider requests.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import plistlib
import shlex
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import mm_core as core
import mm_runtime_guards as guards

UTC = dt.timezone.utc
ROOT = core.root()
PY = str(ROOT / ".venv-email/bin/python")
PLIST = Path.home() / "Library/LaunchAgents/ai.website-auditor.supervisor.plist"


def run(command):
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True,
                            timeout=30, check=False)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {command[0]}")
    return result.stdout.strip()


def git_info():
    return {"sha": run(["git", "rev-parse", "HEAD"]),
            "branch": run(["git", "symbolic-ref", "--short", "HEAD"]),
            "working_tree_clean": not run(["git", "status", "--porcelain"])}


def supervisor_processes():
    processes = []
    for line in run(["ps", "-ax", "-o", "pid=,stat=,command="]).splitlines():
        fields = line.strip().split(None, 2)
        if len(fields) != 3 or fields[1].startswith("Z"):
            continue
        if "supervisor.cli" not in fields[2] or "_run-foreground" not in fields[2]:
            continue
        tokens = shlex.split(fields[2])
        if "supervisor.cli" in tokens and "_run-foreground" in tokens:
            processes.append({"pid": int(fields[0]), "interpreter": tokens[0]})
    return processes


def service_config():
    """Hash private configuration without copying its contents into evidence."""
    if not (ROOT / ".venv-email/pyvenv.cfg").is_file():
        raise FileNotFoundError("project virtualenv configuration is missing")
    hashes = {}
    for path in (ROOT / ".env", ROOT / ".env.fcc",
                 ROOT / ".venv-email/pyvenv.cfg", PLIST):
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    with PLIST.open("rb") as fh:
        config = plistlib.load(fh)
    return {"hashes": hashes, "program": config.get("ProgramArguments", [None])[0],
            "working_directory": config.get("WorkingDirectory"),
            "external_send_disabled": config.get("EnvironmentVariables", {}).get(
                "MM_EXTERNAL_SEND_DISABLED"),
            "root": config.get("EnvironmentVariables", {}).get("MM_ROOT")}


def database_diagnostics():
    path = ROOT / "database/money_machine.db"
    with contextlib.closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True,
                                          timeout=10)) as d:
        d.execute("BEGIN")
        return {"integrity_check": d.execute("PRAGMA integrity_check").fetchone()[0],
                "foreign_key_errors": [list(r) for r in d.execute("PRAGMA foreign_key_check")],
                "pipeline_states": dict(d.execute(
                    "SELECT state,count(*) FROM pipeline_items GROUP BY state")),
                "dead_lettered": d.execute(
                    "SELECT count(*) FROM pipeline_items WHERE state IN "
                    "('RETRYABLE_FAILURE','PERMANENT_FAILURE')").fetchone()[0],
                "active_leases": d.execute(
                    "SELECT count(*) FROM pipeline_items WHERE lease_until>?",
                    (core.now(),)).fetchone()[0],
                "expired_leases": d.execute(
                    "SELECT count(*) FROM pipeline_items WHERE lease_until IS NOT NULL "
                    "AND lease_until<=?", (core.now(),)).fetchone()[0]}


def collect_sample(label="sample"):
    snapshot = {"label": label, "sampling_started_at_utc": core.now(),
                "monitor_python": sys.executable, "errors": {}}
    readers = {
        "git": git_info,
        "supervisor_processes": supervisor_processes,
        "config": service_config,
        "db": database_diagnostics,
        "accounting": lambda: guards.accounting_snapshot(ROOT),
        "heartbeat": lambda: json.loads((ROOT / "state/supervisor.heartbeat").read_text()),
        "pidfile": lambda: int((ROOT / "state/supervisor.pid").read_text()),
        "launchd": lambda: run(["launchctl", "print",
                               f"gui/{os.getuid()}/ai.website-auditor.supervisor"]),
        "disk": lambda: guards.disk_guard(ROOT),
        "network_probe": lambda: guards.network_guard(
            hosts=["example.com:443", "github.com:443"], use_cache=False),
    }
    for name, reader in readers.items():
        try:
            snapshot[name] = reader()
        except Exception as exc:
            snapshot[name] = None
            snapshot["errors"][name] = f"{type(exc).__name__}: {exc}"
    # Do not retain launchctl's complete environment in evidence.
    launchd = snapshot.pop("launchd")
    snapshot["launchd_running"] = bool(
        launchd and "state = running" in launchd
        and f"pid = {snapshot.get('pidfile')}" in launchd)
    # The heartbeat may advance while the earlier readers are running.
    # Timestamp the completed sample after reading it to avoid a negative age.
    snapshot["collected_at_utc"] = core.now()
    return snapshot


def detect_violations(snapshot, baseline=None, previous=None,
                      heartbeat_max_age=180, max_gap=420):
    violations = []
    if snapshot.get("errors"):
        violations.append("required evidence unavailable: " + ", ".join(snapshot["errors"]))
    git = snapshot.get("git") or {}
    if not git.get("working_tree_clean") or len(git.get("sha", "")) != 40:
        violations.append("revision missing or working tree dirty")
    procs = snapshot.get("supervisor_processes") or []
    pid = snapshot.get("pidfile")
    if len(procs) != 1 or procs[0].get("pid") != pid:
        violations.append("supervisor count or pidfile ownership mismatch")
    elif procs[0].get("interpreter") != PY:
        violations.append("supervisor interpreter differs from project virtualenv")
    if not snapshot.get("launchd_running"):
        violations.append("launchd does not own the running supervisor")
    config = snapshot.get("config") or {}
    if (config.get("external_send_disabled") != "1"
            or config.get("program") != PY or config.get("root") != str(ROOT)
            or config.get("working_directory") != str(ROOT / "money-machine")):
        violations.append("service configuration or send-disabled gate mismatch")
    hb = snapshot.get("heartbeat") or {}
    try:
        age = (core.timestamp(snapshot["collected_at_utc"]) - core.timestamp(hb["at"])).total_seconds()
        if (not 0 <= age <= heartbeat_max_age or hb.get("pid") != pid
                or hb.get("status") != "running"):
            violations.append("heartbeat stale, stopped, paused, or mismatched")
    except (ValueError, TypeError, KeyError):
        violations.append("heartbeat evidence missing or invalid")
    accounting = snapshot.get("accounting") or {}
    if accounting.get("status") != "measured":
        violations.append("accounting unavailable or invalid")
    elif (accounting.get("paid_calls") != 0 or accounting.get("model_cost_usd") != 0
          or accounting.get("external_sends") != 0 or accounting.get("invalid_cost_records") != 0):
        violations.append("recorded cost, sends, or invalid cost records")
    db = snapshot.get("db") or {}
    if db.get("integrity_check") != "ok" or db.get("foreign_key_errors") != []:
        violations.append("database integrity evidence failed or missing")
    if db.get("dead_lettered") is None or db.get("expired_leases") != 0:
        violations.append("dead-letter evidence missing or expired leases present")
    if (snapshot.get("disk") or {}).get("ok") is not True:
        violations.append("disk below minimum or evidence unavailable")
    if (snapshot.get("network_probe") or {}).get("ok") is not True:
        violations.append("explicit public network probe failed or missing")
    if baseline:
        if git != baseline.get("git"):
            violations.append("revision, branch, or working-tree state changed")
        if config != baseline.get("config"):
            violations.append("service configuration changed")
        if pid != baseline.get("pidfile"):
            violations.append("supervisor PID changed")
        start_dead = (baseline.get("db") or {}).get("dead_lettered")
        if start_dead is None or db.get("dead_lettered") is None or db["dead_lettered"] > start_dead:
            violations.append("dead-letter count grew or comparison unavailable")
    if previous:
        gap = (core.timestamp(snapshot["collected_at_utc"])
               - core.timestamp(previous["collected_at_utc"])).total_seconds()
        if not 0 < gap <= max_gap:
            violations.append(f"sample gap out of bounds: {gap:.1f}s")
    return violations


def summarize(samples, violations, duration, completed, reason=None,
              max_gap=420, heartbeat_max_age=180):
    start, finish = samples[0], samples[-1]
    elapsed = (core.timestamp(finish["collected_at_utc"])
               - core.timestamp(start["collected_at_utc"])).total_seconds()
    result = {"test": "money-machine-supervisor-24h-soak",
              "status": "completed" if completed else "incomplete",
              "reason": reason, "soak_start_utc": start["collected_at_utc"],
              "soak_finish_utc": finish["collected_at_utc"],
              "soak_target_end_utc": (
                  core.timestamp(start["collected_at_utc"]) + dt.timedelta(seconds=duration)).isoformat(),
              "actual_elapsed_seconds": elapsed, "target_seconds": duration,
              "sample_count": len(samples), "soak_start_sha": (start.get("git") or {}).get("sha"),
              "soak_finish_sha": (finish.get("git") or {}).get("sha"),
              "violations": violations, "accounting_limitation": "database records only"}
    gates = {
        "duration_meets_24h": duration >= 86400 and elapsed >= duration,
        "monitor_completed": completed,
        "all_samples_valid": not violations and len(samples) >= 2,
        "revision_frozen": all(s.get("git") == start.get("git") for s in samples),
        "complete_sample_coverage": all(
            0 < (core.timestamp(b["collected_at_utc"])
                 - core.timestamp(a["collected_at_utc"])).total_seconds() <= max_gap
            for a, b in zip(samples, samples[1:])),
    }
    # Independently recalculate all gates at finish; callers cannot bypass a
    # missing intermediate sample check by supplying an empty violations list.
    gates["evidence_valid"] = all(not detect_violations(
        sample, start, samples[index - 1] if index else None,
        heartbeat_max_age, max_gap) for index, sample in enumerate(samples))
    result.update(acceptance=gates, soak_passed=all(gates.values()))
    return result


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    os.replace(temporary, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--duration", type=int, default=86400)
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument("--max-gap", type=int, default=420)
    parser.add_argument("--heartbeat-max-age", type=int, default=180)
    args = parser.parse_args(argv)
    if not (1 <= args.duration <= 604800 and 1 <= args.interval <= 3600
            and args.interval < args.max_gap <= 7200 and 1 <= args.heartbeat_max_age <= 600):
        parser.error("invalid bounded duration, interval, gap, or heartbeat age")
    directory = args.directory or ROOT / "state" / (
        "soak-evidence-" + dt.datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    (ROOT / "state").mkdir(exist_ok=True)
    with (ROOT / "state/soak-monitor.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("a soak monitor already holds the repository lock")
        directory.mkdir(parents=True, exist_ok=False)
        write_json(directory / "monitor.json", {"pid": os.getpid(), "python": sys.executable,
                   "module": str(Path(__file__)),
                   "module_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   "arguments": vars(args) | {"directory": str(directory)}})
        # A TERM must leave explicit incomplete evidence rather than silently
        # disappearing. A hard kill is detected by absent finish evidence.
        def interrupted(signum, frame):
            raise KeyboardInterrupt(f"signal {signum}")

        signal.signal(signal.SIGTERM, interrupted)
        samples, violations = [], []
        completed, reason = False, None
        start = collect_sample("soak_start")
        samples.append(start)
        start_errors = detect_violations(start, heartbeat_max_age=args.heartbeat_max_age)
        if start_errors:
            violations.append({"sample": 0, "violations": start_errors})
        write_json(directory / "soak-start.json", start)
        write_json(directory / "soak-status.json", {
            "status": "preflight_failed" if start_errors else "in_progress",
            "soak_passed": False, "start_utc": start["collected_at_utc"],
            "target_end_utc": (core.timestamp(start["collected_at_utc"])
                               + dt.timedelta(seconds=args.duration)).isoformat(),
            "interval_seconds": args.interval, "max_gap_seconds": args.max_gap,
            "heartbeat_max_age_seconds": args.heartbeat_max_age})
        deadline = time.monotonic() + args.duration
        with (directory / "soak-samples.jsonl").open("x") as stream:
            def append(sample):
                stream.write(json.dumps(sample) + "\n")
                stream.flush()
                os.fsync(stream.fileno())

            append(start)
            print(f"SOAK directory={directory} pid={os.getpid()} start={start['collected_at_utc']}",
                  flush=True)
            try:
                if start_errors:
                    reason = "preflight acceptance failed"
                else:
                    while time.monotonic() < deadline:
                        time.sleep(min(args.interval, max(0, deadline - time.monotonic())))
                        sample = collect_sample(f"sample_{len(samples)}")
                        errors = detect_violations(sample, start, samples[-1],
                                                   args.heartbeat_max_age, args.max_gap)
                        samples.append(sample)
                        append(sample)
                        if errors:
                            violations.append({"sample": len(samples) - 1, "violations": errors})
                        write_json(directory / "soak-violations.json", violations)
                        print(f"sample={len(samples)-1} at={sample['collected_at_utc']} "
                              f"violations={errors}", flush=True)
                    completed = True
            except (KeyboardInterrupt, Exception) as exc:
                reason = f"{type(exc).__name__}: {exc}"
                # Include a final timestamp so the final sample gap is checked.
                sample = collect_sample("soak_interrupted")
                errors = detect_violations(sample, start, samples[-1],
                                           args.heartbeat_max_age, args.max_gap)
                samples.append(sample)
                append(sample)
                violations.append({"sample": len(samples) - 1,
                                   "violations": [reason] + errors})
        summary = summarize(samples, violations, args.duration, completed, reason,
                            args.max_gap, args.heartbeat_max_age)
        write_json(directory / "soak-summary.json", summary)
        write_json(directory / "soak-finish.json", samples[-1])
        write_json(directory / "soak-status.json", summary)
        print(f"SOAK status={summary['status']} passed={summary['soak_passed']}", flush=True)
        return 0 if summary["soak_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
