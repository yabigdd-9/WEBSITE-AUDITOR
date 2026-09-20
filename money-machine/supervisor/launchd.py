#!/usr/bin/env python3
"""Install/remove the user launchd service for WEBSITE-AUDITOR.

The launchd job runs the supervisor in the foreground. launchd owns restart
semantics; SupervisorDaemon owns the exclusive lock and child restart policy.
External sending is forcibly disabled in the environment.
"""
from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = REPO_ROOT / "state"
LABEL = "ai.website-auditor.supervisor"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def python_path() -> Path:
    configured = os.environ.get("MM_PYTHON")
    if configured:
        return Path(configured).expanduser().resolve()
    return (REPO_ROOT / ".venv-email" / "bin" / "python").resolve()


def service_path() -> Path:
    return (REPO_ROOT / "money-machine" / "supervisor" / "service.py").resolve()


def plist_payload(
    sleep: float = 60,
    heartbeat: float = 5,
    lease: int = 300,
    report_every: int = 10,
    max_backoff: float = 60,
) -> dict:
    py = python_path()
    service = service_path()
    args = [
        str(py),
        str(service),
        "run",
        "--sleep",
        str(sleep),
        "--heartbeat",
        str(heartbeat),
        "--lease",
        str(lease),
        "--report-every",
        str(report_every),
        "--max-backoff",
        str(max_backoff),
    ]
    return {
        "Label": LABEL,
        "ProgramArguments": args,
        "WorkingDirectory": str(REPO_ROOT),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "ThrottleInterval": 10,
        "EnvironmentVariables": {
            "MM_ROOT": str(REPO_ROOT),
            "MM_EXTERNAL_SEND_DISABLED": "1",
            "PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin",
        },
        "StandardOutPath": str(STATE_DIR / "launchd-supervisor.stdout.log"),
        "StandardErrorPath": str(STATE_DIR / "launchd-supervisor.stderr.log"),
    }


def write_plist(**kwargs) -> Path:
    py = python_path()
    service = service_path()
    if not py.is_file():
        raise FileNotFoundError(f"Python runtime missing: {py}")
    if not service.is_file():
        raise FileNotFoundError(f"Supervisor service missing: {service}")
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_bytes(
        plistlib.dumps(plist_payload(**kwargs), fmt=plistlib.FMT_XML, sort_keys=True)
    )
    return PLIST_PATH


def _domain() -> str:
    return f"gui/{os.getuid()}"


def install(load: bool = True, **kwargs) -> dict:
    path = write_plist(**kwargs)
    result = {"installed": True, "plist": str(path), "loaded": False, "label": LABEL}
    if not load:
        return result

    subprocess.run(
        ["launchctl", "bootout", _domain(), str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    proc = subprocess.run(
        ["launchctl", "bootstrap", _domain(), str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    result["loaded"] = proc.returncode == 0
    if proc.returncode != 0:
        result["error"] = (proc.stderr or proc.stdout).strip()
    return result


def uninstall(remove: bool = True) -> dict:
    proc = subprocess.run(
        ["launchctl", "bootout", _domain(), str(PLIST_PATH)],
        capture_output=True,
        text=True,
        check=False,
    )
    existed = PLIST_PATH.exists()
    if remove:
        PLIST_PATH.unlink(missing_ok=True)
    return {
        "uninstalled": True,
        "was_present": existed,
        "plist_removed": remove and not PLIST_PATH.exists(),
        "bootout_returncode": proc.returncode,
    }


def status() -> dict:
    proc = subprocess.run(
        ["launchctl", "print", f"{_domain()}/{LABEL}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "label": LABEL,
        "plist": str(PLIST_PATH),
        "plist_exists": PLIST_PATH.exists(),
        "loaded": proc.returncode == 0,
    }


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("install")
    q.add_argument("--no-load", action="store_true")
    q.add_argument("--sleep", type=float, default=60)
    q.add_argument("--heartbeat", type=float, default=5)
    q.add_argument("--lease", type=int, default=300)
    q.add_argument("--report-every", type=int, default=10)
    q.add_argument("--max-backoff", type=float, default=60)

    sub.add_parser("status")
    q = sub.add_parser("uninstall")
    q.add_argument("--keep-plist", action="store_true")
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if args.cmd == "install":
        result = install(
            load=not args.no_load,
            sleep=args.sleep,
            heartbeat=args.heartbeat,
            lease=args.lease,
            report_every=args.report_every,
            max_backoff=args.max_backoff,
        )
        print(result)
        return 0 if result.get("installed") else 2
    if args.cmd == "status":
        print(status())
        return 0
    if args.cmd == "uninstall":
        print(uninstall(remove=not args.keep_plist))
        return 0
    raise AssertionError(args.cmd)


if __name__ == "__main__":
    raise SystemExit(main())
