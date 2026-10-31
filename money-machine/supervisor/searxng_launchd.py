#!/usr/bin/env python3
"""User-scoped launchd manager for the local loopback SearXNG service."""
from __future__ import annotations

import argparse
import os
import plistlib
import socket
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = REPO_ROOT / "state"
LABEL = "ai.website-auditor.searxng"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / (LABEL + ".plist")
PYTHON = Path.home() / ".local" / "share" / "searxng" / ".venv" / "bin" / "python"
SETTINGS = Path.home() / ".searxng" / "settings.yml"


def _domain():
    return "gui/" + str(os.getuid())


def plist_payload():
    return {
        "Label": LABEL,
        "ProgramArguments": [str(PYTHON), "-m", "searx.webapp"],
        "WorkingDirectory": str(Path.home()),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "ThrottleInterval": 10,
        "EnvironmentVariables": {
            "SEARXNG_SETTINGS_PATH": str(SETTINGS),
            "PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin",
        },
        "StandardOutPath": str(STATE_DIR / "launchd-searxng.stdout.log"),
        "StandardErrorPath": str(STATE_DIR / "launchd-searxng.stderr.log"),
    }


def write_plist():
    if not PYTHON.is_file():
        raise FileNotFoundError("SearXNG Python missing: " + str(PYTHON))
    if not SETTINGS.is_file():
        raise FileNotFoundError("SearXNG settings missing: " + str(SETTINGS))
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
        "host": "127.0.0.1",
        "port": 8888,
        "error": "" if proc.returncode == 0 else (proc.stderr or proc.stdout).strip(),
    }


def _pid_file():
    """Return the optional SearXNG PID file path (for non-launchd management)."""
    return STATE_DIR / "searxng.pid"


def _pid_alive(pid):
    """Return True if the given PID belongs to a live process."""
    if not pid or pid <= 0:
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


def _is_listening(host, port, timeout=3):
    """Independently verify a TCP listener is accepting on host:port (loopback only)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def status():
    proc = subprocess.run(
        ["launchctl", "print", _domain() + "/" + LABEL],
        capture_output=True,
        text=True,
        check=False,
    )
    loaded = proc.returncode == 0

    # PID-file-managed check (when SearXNG runs outside launchd).
    pid = None
    pid_alive = False
    pid_file = _pid_file()
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
        except (OSError, ValueError):
            pid = None
        if pid:
            pid_alive = _pid_alive(pid)

    # Independent, accurate loopback listener check.
    listening = _is_listening("127.0.0.1", 8888)

    # running spans both management modes: a live PID file OR a reachable
    # listener (covers launchd-managed instances that have no PID file).
    running = pid_alive or listening

    return {
        "label": LABEL,
        "plist_exists": PLIST_PATH.exists(),
        "loaded": loaded,
        "running": running,
        "listening": listening,
        "pid": pid if pid_alive else None,
        "pidfile": str(pid_file) if pid_file.exists() else None,
        "python_exists": PYTHON.is_file(),
        "settings_exists": SETTINGS.is_file(),
        "host": "127.0.0.1",
        "port": 8888,
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
