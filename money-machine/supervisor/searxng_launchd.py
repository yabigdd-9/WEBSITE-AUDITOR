#!/usr/bin/env python3
"""User-scoped launchd wrapper for the local SearXNG discovery service.

Mirrors the pattern in launchd.py: launchd owns host restart semantics;
this module owns single-instance PID lock + plist generation + start/stop/status.

Pre-conditions:
  * SearXNG venv lives at ~/.local/share/searxng/.venv
  * Settings live at ~/.searxng/settings.yml
  * The SearXNG process is read-only discovery only; it never sends.

The SearXNG service is bound to 127.0.0.1:8888 and is optional — when absent,
discovery CLI commands raise a typed SearchBlocked error rather than falling
back to an external service.
"""
from __future__ import annotations

import argparse
import json
import os
import plistlib
import signal
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = REPO_ROOT / "state"
PIDFILE = STATE_DIR / "searxng.pid"
LOG_DIR = STATE_DIR / "worker-logs"
LABEL = "ai.website-auditor.searxng"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / (LABEL + ".plist")

DEFAULT_VENV = Path.home() / ".local" / "share" / "searxng" / ".venv"
DEFAULT_SETTINGS = Path.home() / ".searxng" / "settings.yml"


def _python() -> Path:
    venv_python = DEFAULT_VENV / "bin" / "python"
    if venv_python.is_file():
        return venv_python
    raise FileNotFoundError(
        "SearXNG venv missing at %s — run 'pip install -e .' in ~/.local/share/searxng" % str(DEFAULT_VENV)
    )


def _existing_pid() -> int | None:
    try:
        return int(PIDFILE.read_text().strip())
    except (OSError, ValueError):
        return None


def _is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _is_listening(endpoint: str = "http://127.0.0.1:8888") -> bool:
    import urllib.request, urllib.error
    try:
        req = urllib.request.Request(endpoint, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status in (200, 404)  # 404 is fine, it means SearXNG answered
    except Exception:
        return False


def status() -> dict:
    pid = _existing_pid()
    # If PIDFILE shows a process, check it; otherwise check launchd
    running = _is_running(pid) if pid else False
    listen_result = _is_listening()
    if not running and pid is None:
        # Process is managed by launchd, not our pidfile — check listening directly
        running = listen_result
    return {
        "label": LABEL,
        "pid": pid if running else None,
        "running": running,
        "listening": listen_result,
        "plist": str(PLIST_PATH),
        "plist_exists": PLIST_PATH.exists(),
        "loaded": _launchd_loaded(),
        "venv": str(_python()),
        "settings": str(DEFAULT_SETTINGS) if DEFAULT_SETTINGS.is_file() else None,
    }


def _launchd_loaded() -> bool:
    try:
        proc = subprocess.run(
            ["launchctl", "print", "gui/%s/%s" % (os.getuid(), LABEL)],
            capture_output=True, text=True,
        )
        return proc.returncode == 0
    except Exception:
        return False


def plist_payload() -> dict:
    py = _python()
    env = dict(os.environ)
    env["SEARXNG_SETTINGS_PATH"] = str(DEFAULT_SETTINGS) if DEFAULT_SETTINGS.is_file() else ""
    env["MM_EXTERNAL_SEND_DISABLED"] = "1"
    env_clean = {k: v for k, v in env.items() if isinstance(v, str)}
    return {
        "Label": LABEL,
        "ProgramArguments": [
            str(py), "-m", "searx.webapp", "--logging-level", "WARNING",
        ],
        "WorkingDirectory": str(REPO_ROOT),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "ThrottleInterval": 10,
        "EnvironmentVariables": {
            **env_clean,
            "SEARXNG_SETTINGS_PATH": str(DEFAULT_SETTINGS),
        },
        "StandardOutPath": str(LOG_DIR / "searxng.stdout.log"),
        "StandardErrorPath": str(LOG_DIR / "searxng.stderr.log"),
    }


def write_plist() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_bytes(plistlib.dumps(plist_payload(), fmt=plistlib.FMT_XML, sort_keys=True))
    return PLIST_PATH


def install(load: bool = True) -> dict:
    py = _python()
    if not py.is_file():
        raise FileNotFoundError("SearXNG venv python missing: %s" % str(py))
    write_plist()
    result = {"installed": True, "loaded": False, "label": LABEL, "plist": str(PLIST_PATH)}
    if not load:
        return result
    # launchctl bootout takes the full target (gui/<uid>/<label>); bootstrap takes domain (gui/<uid>) + plist path
    domain = "gui/%s" % os.getuid()
    target = "%s/%s" % (domain, LABEL)
    subprocess.run(
        ["launchctl", "bootout", target, str(PLIST_PATH)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    proc = subprocess.run(
        ["launchctl", "bootstrap", domain, str(PLIST_PATH)],
        capture_output=True, text=True, check=False,
    )
    result["loaded"] = proc.returncode == 0
    if proc.returncode != 0:
        result["error"] = (proc.stderr or proc.stdout).strip()
    return result


def uninstall(remove: bool = True) -> dict:
    proc = subprocess.run(
        ["launchctl", "bootout", "gui/%s/%s" % (os.getuid(), LABEL)],
        capture_output=True, text=True, check=False,
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


def start(use_launchd: bool = True) -> dict:
    if use_launchd:
        result = install(load=True)
        if result.get("loaded"):
            time.sleep(2)
        return result
    # Manual start: spawn the process directly
    pid = _existing_pid()
    if pid and _is_running(pid):
        return {"started": False, "pid": pid, "reason": "already running"}
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stdout = open(LOG_DIR / "searxng.stdout.log", "ab")
    stderr = open(LOG_DIR / "searxng.stderr.log", "ab")
    env = dict(os.environ)
    env["SEARXNG_SETTINGS_PATH"] = str(DEFAULT_SETTINGS)
    proc = subprocess.Popen(
        [str(_python()), "-m", "searx.webapp", "--logging-level", "WARNING"],
        stdout=stdout, stderr=stderr,
        env=env,
        start_new_session=True,
    )
    PIDFILE.write_text(str(proc.pid))
    return {"started": True, "pid": proc.pid, "pidfile": str(PIDFILE)}


def stop() -> dict:
    pid = _existing_pid()
    if not pid or not _is_running(pid):
        PIDFILE.unlink(missing_ok=True)
        return {"stopped": True, "was_running": False}
    os.kill(pid, signal.SIGTERM)
    for _ in range(10):
        if not _is_running(pid):
            break
        time.sleep(0.5)
    if _is_running(pid):
        os.kill(pid, signal.SIGKILL)
    PIDFILE.unlink(missing_ok=True)
    return {"stopped": True, "was_running": True, "pid": pid}


def ensure_running() -> dict:
    st = status()
    if st["listening"]:
        return {"running": True, "pid": st["pid"], "action": "none"}
    if st["running"] and not st["listening"]:
        stop()
    result = start(use_launchd=False)
    return result


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="SearXNG local discovery service wrapper")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("start")
    sub.add_parser("stop")
    sub.add_parser("restart")
    sub.add_parser("ensure-running")
    q = sub.add_parser("install")
    q.add_argument("--no-load", action="store_true")
    sub.add_parser("uninstall")
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if args.cmd == "status":
        print(json.dumps(status(), indent=2))
        return 0
    if args.cmd == "install":
        result = install(load=not args.no_load)
        print(json.dumps(result, indent=2))
        return 0 if result.get("installed") else 2
    if args.cmd == "uninstall":
        print(json.dumps(uninstall(), indent=2))
        return 0
    if args.cmd == "start":
        print(json.dumps(start(), indent=2))
        return 0
    if args.cmd == "stop":
        print(json.dumps(stop(), indent=2))
        return 0
    if args.cmd == "restart":
        stop()
        result = start()
        print(json.dumps(result, indent=2))
        return 0
    if args.cmd == "ensure-running":
        print(json.dumps(ensure_running(), indent=2))
        return 0
    raise AssertionError(args.cmd)


if __name__ == "__main__":
    raise SystemExit(main())
