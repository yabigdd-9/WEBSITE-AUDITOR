#!/usr/bin/env python3
"""Continuous, local-first Website Auditor monitor.

Runs bounded audits on an explicit target list, stores timestamped artifacts, ingests
them into SQLite history, and emits regression alerts. No outreach/send actions occur.
"""
from __future__ import annotations

import argparse
import json
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
_STOP = False


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_domain(url: str) -> str:
    candidate = url if "://" in url else "https://" + url
    host = (urlsplit(candidate).hostname or "site").lower()
    return re.sub(r"[^a-z0-9_.-]", "_", host)


def load_targets(values: list[str] | None, target_file: str | None) -> list[str]:
    targets: list[str] = []
    for value in values or []:
        value = value.strip()
        if value and value not in targets:
            targets.append(value)
    if target_file:
        for raw in Path(target_file).read_text().splitlines():
            value = raw.strip()
            if not value or value.startswith("#"):
                continue
            if value not in targets:
                targets.append(value)
    return targets


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str))
    tmp.replace(path)


def run_command(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True)


def audit_target(
    target: str,
    *,
    profile: str,
    crawl: bool,
    max_pages: int | None,
    history_db: Path,
    alerts_dir: Path,
) -> dict:
    domain = safe_domain(target)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_dir = ROOT / "outputs" / "monitor" / "audits" / domain
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive = archive_dir / f"{stamp}.json"

    command = [
        sys.executable,
        "website_auditor.py",
        target,
        "--format",
        "json",
        "--output",
        str(archive),
        "--profile",
        profile,
        "--mode",
        "static",
    ]
    if crawl:
        command.append("--crawl")
        if max_pages is not None:
            command.extend(["--max-pages", str(max_pages)])

    started = time.monotonic()
    result = run_command(command)
    duration = round(time.monotonic() - started, 3)
    record = {
        "target": target,
        "domain": domain,
        "started_at": utc_now(),
        "duration_seconds": duration,
        "audit_file": str(archive),
        "audit_exit_code": result.returncode,
        "stdout_tail": result.stdout[-2000:],
        "stderr_tail": result.stderr[-2000:],
        "history": None,
    }
    if result.returncode != 0 or not archive.exists():
        record["status"] = "audit_failed"
        return record

    latest = ROOT / "audits" / f"{domain}.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_bytes(archive.read_bytes())

    history = run_command([
        sys.executable,
        "audit-history.py",
        "--db",
        str(history_db),
        "--alerts-dir",
        str(alerts_dir),
        "ingest",
        str(archive),
    ])
    record["history"] = {
        "exit_code": history.returncode,
        "stdout_tail": history.stdout[-4000:],
        "stderr_tail": history.stderr[-2000:],
    }
    record["status"] = "ok" if history.returncode == 0 else "history_failed"
    return record


def monitor_cycle(args) -> dict:
    targets = load_targets(args.target, args.targets_file)
    if not targets:
        raise SystemExit("No targets supplied. Use --target or --targets-file.")

    results = []
    for target in targets:
        if _STOP:
            break
        results.append(
            audit_target(
                target,
                profile=args.profile,
                crawl=args.crawl,
                max_pages=args.max_pages,
                history_db=Path(args.db),
                alerts_dir=Path(args.alerts_dir),
            )
        )

    cycle = {
        "schema_version": 1,
        "cycle_completed_at": utc_now(),
        "target_count": len(targets),
        "processed_count": len(results),
        "success_count": sum(item["status"] == "ok" for item in results),
        "failure_count": sum(item["status"] != "ok" for item in results),
        "results": results,
    }
    atomic_json(Path(args.state_file), cycle)
    return cycle


def request_stop(signum, frame) -> None:
    global _STOP
    _STOP = True


def main() -> None:
    parser = argparse.ArgumentParser(description="Continuous Website Auditor monitor")
    parser.add_argument("--target", action="append", help="Target URL; repeat for multiple sites")
    parser.add_argument("--targets-file", help="Text file with one URL per line")
    parser.add_argument(
        "--profile",
        choices=["quick", "standard", "deep", "ecommerce", "leadgen", "nz_small_business"],
        default="standard",
    )
    parser.add_argument("--crawl", action="store_true")
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--watch", action="store_true", help="Repeat continuously")
    parser.add_argument("--interval", type=int, default=3600, help="Seconds between cycle starts")
    parser.add_argument("--state-file", default="outputs/monitor/state.json")
    parser.add_argument("--db", default="outputs/history/audits.sqlite3")
    parser.add_argument("--alerts-dir", default="outputs/regressions")
    args = parser.parse_args()

    if args.interval < 300:
        parser.error("--interval must be at least 300 seconds")
    if args.max_pages is not None and not args.crawl:
        parser.error("--max-pages requires --crawl")
    if args.max_pages is not None and not 1 <= args.max_pages <= 50:
        parser.error("--max-pages must be between 1 and 50")

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    while True:
        cycle_started = time.monotonic()
        report = monitor_cycle(args)
        print(json.dumps(report, indent=2, default=str), flush=True)

        if not args.watch or _STOP:
            break
        elapsed = time.monotonic() - cycle_started
        sleep_for = max(0, args.interval - elapsed)
        deadline = time.monotonic() + sleep_for
        while not _STOP and time.monotonic() < deadline:
            time.sleep(min(5.0, deadline - time.monotonic()))


if __name__ == "__main__":
    main()
