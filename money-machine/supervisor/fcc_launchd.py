#!/usr/bin/env python3
"""User-scoped launchd wrapper for the loopback FCC server."""
from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = REPO_ROOT / "state"
LABEL = "ai.website-auditor.fcc"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / (LABEL + ".plist")
WRAPPER = REPO_ROOT / "scripts" / "fcc-server-wrapper.sh"


def _domain():
    return "gui/" + str(os.getuid())


def plist_payload():
    return {
        "Label": LABEL,
        "ProgramArguments": ["/bin/sh", str(WRAPPER)],
        "WorkingDirectory": str(REPO_ROOT),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "ThrottleInterval": 10,
        "EnvironmentVariables": {
            "HOST": "127.0.0.1",
            "PORT": "8082",
            "PATH": str(Path.home() / ".local/bin") + ":/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin",
        },
        "StandardOutPath": str(STATE_DIR / "launchd-fcc.stdout.log"),
        "StandardErrorPath": str(STATE_DIR / "launchd-fcc.stderr.log"),
    }


def write_plist():
    if not WRAPPER.is_file():
        raise FileNotFoundError("FCC wrapper missing: " + str(WRAPPER))
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_bytes(
        plistlib.dumps(plist_payload(), fmt=plistlib.FMT_XML, sort_keys=True)
    )
    return PLIST_PATH


def install():
    path = write_plist()
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
    return {
        "installed": True,
        "loaded": proc.returncode == 0,
        "label": LABEL,
        "plist": str(path),
        "error": "" if proc.returncode == 0 else (proc.stderr or proc.stdout).strip(),
    }


def status():
    proc = subprocess.run(
        ["launchctl", "print", _domain() + "/" + LABEL],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "label": LABEL,
        "plist_exists": PLIST_PATH.exists(),
        "loaded": proc.returncode == 0,
        "host": "127.0.0.1",
        "port": 8082,
    }


def uninstall():
    proc = subprocess.run(
        ["launchctl", "bootout", _domain(), str(PLIST_PATH)],
        capture_output=True,
        text=True,
        check=False,
    )
    existed = PLIST_PATH.exists()
    PLIST_PATH.unlink(missing_ok=True)
    return {
        "uninstalled": True,
        "was_present": existed,
        "bootout_returncode": proc.returncode,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["install", "status", "uninstall"])
    args = p.parse_args(argv)
    result = globals()[args.action]()
    print(result)
    if args.action == "install":
        return 0 if result.get("loaded") else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
