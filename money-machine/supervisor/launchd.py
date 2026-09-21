#!/usr/bin/env python3
"""User-scoped launchd wrapper for the current WEBSITE-AUDITOR supervisor CLI.

launchd owns host restart semantics. The existing supervisor CLI owns the
single-instance lock, worker lifecycle, leases, retries, heartbeats and logs.
External send is explicitly disabled in the launchd environment.
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
        return Path(configured).expanduser().resolve()
    return (REPO_ROOT / ".venv-email" / "bin" / "python").resolve()


def plist_payload(sleep: float = 5, lease: int = 300, rotate_every: int = 60) -> dict:
    return {
        "Label": LABEL,
        "ProgramArguments": [
            str(python_path()),
            "-m",
            "supervisor.cli",
            "_run-foreground",
            "--sleep",
            str(sleep),
            "--lease",
            str(lease),
            "--rotate-every",
            str(rotate_every),
        ],
        "WorkingDirectory": str(MM_DIR),
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
    cli = MM_DIR / "supervisor" / "cli.py"
    if not py.is_file():
        raise FileNotFoundError("Python runtime missing: " + str(py))
    if not cli.is_file():
        raise FileNotFoundError("Supervisor CLI missing: " + str(cli))
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
    q.add_argument("--sleep", type=float, default=5)
    q.add_argument("--lease", type=int, default=300)
    q.add_argument("--rotate-every", type=int, default=60)
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
            lease=args.lease,
            rotate_every=args.rotate_every,
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
