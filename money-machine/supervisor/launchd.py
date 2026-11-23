#!/usr/bin/env python3
"""User-scoped launchd liveness check for the WEBSITE-AUDITOR supervisor.

launchd periodically invokes the existing idempotent ``ensure-running`` CLI.
That CLI owns the supervisor's PID lock, worker lifecycle, leases, retries,
heartbeats and logs. External send stays explicitly disabled.
"""
from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MM_DIR = REPO_ROOT / "money-machine"
STATE_DIR = REPO_ROOT / "state"
LABEL = "ai.website-auditor.supervisor"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / (LABEL + ".plist")


def python_path() -> Path:
    configured = os.environ.get("MM_PYTHON", "").strip()
    if configured:
        # Preserve the virtualenv entry point. Resolving its symlink points at
        # the base interpreter and drops the venv's dependency environment.
        return Path(configured).expanduser()
    return REPO_ROOT / ".venv-email" / "bin" / "python"


def plist_payload(interval_seconds: int = 300) -> dict:
    if interval_seconds < 30:
        raise ValueError("launchd supervisor check interval must be at least 30 seconds")
    return {
        "Label": LABEL,
        "ProgramArguments": [
            "/bin/sh",
            "-c",
            'exec "$MM_ROOT/money-machine/mm" supervisor ensure-running',
        ],
        "WorkingDirectory": str(REPO_ROOT),
        "RunAtLoad": True,
        "StartInterval": interval_seconds,
        "ProcessType": "Background",
        "ThrottleInterval": 10,
        "EnvironmentVariables": {
            "MM_ROOT": str(REPO_ROOT),
            "MM_PYTHON": str(python_path()),
            "MM_EXTERNAL_SEND_DISABLED": "1",
            "PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin",
        },
        "StandardOutPath": str(STATE_DIR / "launchd-supervisor.stdout.log"),
        "StandardErrorPath": str(STATE_DIR / "launchd-supervisor.stderr.log"),
    }


def write_plist(**kwargs) -> Path:
    py = python_path()
    operator = MM_DIR / "mm"
    if not py.is_file():
        raise FileNotFoundError("Python runtime missing: " + str(py))
    if not operator.is_file() or not os.access(operator, os.X_OK):
        raise FileNotFoundError("MoneyMachine operator missing or not executable: " + str(operator))
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_bytes(plistlib.dumps(plist_payload(**kwargs), fmt=plistlib.FMT_XML, sort_keys=True))
    return PLIST_PATH


def _domain() -> str:
    return "gui/" + str(os.getuid())


def install(load: bool = True, **kwargs) -> dict:
    path = write_plist(**kwargs)
    result = {"installed": True, "loaded": False, "label": LABEL, "plist": str(path)}
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
        ["launchctl", "print", _domain() + "/" + LABEL],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "label": LABEL,
        "plist": str(PLIST_PATH),
        "plist_exists": PLIST_PATH.exists(),
        "loaded": proc.returncode == 0,
        "external_send_disabled": True,
    }


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("install")
    q.add_argument("--no-load", action="store_true")
    q.add_argument("--interval-seconds", type=int, default=300)
    sub.add_parser("status")
    q = sub.add_parser("uninstall")
    q.add_argument("--keep-plist", action="store_true")
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if args.cmd == "install":
        result = install(
            load=not args.no_load,
            interval_seconds=args.interval_seconds,
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
