#!/usr/bin/env python3
"""Supervisor daemon primitives: exclusive lock, PID, heartbeat and log rotation."""

from __future__ import annotations

import fcntl
import gzip
import json
import os
import signal
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state"
PIDFILE = STATE_DIR / "supervisor.pid"
HEARTBEAT = STATE_DIR / "supervisor.heartbeat"
LOCKFILE = STATE_DIR / "supervisor.lock"
LOG_DIR = STATE_DIR / "worker-logs"


def _pid_is_alive(pid: int) -> bool:
    """Portable process existence check for macOS/Linux without relying on /proc."""
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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SupervisorDaemon:
    def __init__(
        self,
        pidfile: Path = PIDFILE,
        heartbeat: Path = HEARTBEAT,
        lockfile: Path | None = None,
    ):
        self.pidfile = Path(pidfile)
        self.heartbeat = Path(heartbeat)
        self.lockfile = Path(lockfile) if lockfile else self.pidfile.with_suffix(".lock")
        self.running = True
        self._lock_handle = None
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        if signal.getsignal(signal.SIGTERM) is not None:
            signal.signal(signal.SIGTERM, self._on_stop)
            signal.signal(signal.SIGINT, self._on_stop)

    def _on_stop(self, signum, frame):
        self.running = False
        self._cleanup_pidfile()

    def _cleanup_pidfile(self):
        try:
            if self.pidfile.exists() and self.pidfile.read_text().strip() == str(os.getpid()):
                self.pidfile.unlink(missing_ok=True)
        except OSError:
            pass

    def _acquire_lock(self) -> bool:
        self.lockfile.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.lockfile, "a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return False
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        os.fsync(handle.fileno())
        self._lock_handle = handle
        return True

    def start(self) -> bool:
        self.pidfile.parent.mkdir(parents=True, exist_ok=True)
        self.heartbeat.parent.mkdir(parents=True, exist_ok=True)

        if self.pidfile.exists():
            try:
                other_pid = int(self.pidfile.read_text().strip())
                if _pid_is_alive(other_pid):
                    return False
            except (OSError, ValueError):
                pass

        if not self._acquire_lock():
            return False

        self.pidfile.write_text(str(os.getpid()))
        self.tick({"started": _utcnow().isoformat()})
        return True

    def tick(self, extra: dict | None = None) -> dict:
        if not self.running:
            return {"stopped": True}
        payload = {
            "pid": os.getpid(),
            "last_tick": _utcnow().isoformat(),
        }
        if extra:
            payload.update(extra)
        self.heartbeat.write_text(json.dumps(payload, sort_keys=True))
        return {"running": True, **payload, "heartbeat": str(self.heartbeat)}

    def status(self) -> dict:
        pid = None
        if self.pidfile.exists():
            try:
                pid = int(self.pidfile.read_text().strip())
            except (OSError, ValueError):
                pid = None

        heartbeat_data = {}
        heartbeat_age = None
        if self.heartbeat.exists():
            try:
                heartbeat_data = json.loads(self.heartbeat.read_text())
                stamp = heartbeat_data.get("last_tick") or heartbeat_data.get("started")
                if stamp:
                    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                    heartbeat_age = max(0.0, (_utcnow() - parsed).total_seconds())
            except (OSError, ValueError, json.JSONDecodeError):
                heartbeat_data = {}

        return {
            "pidfile_exists": self.pidfile.exists(),
            "heartbeat_exists": self.heartbeat.exists(),
            "running": bool(pid and _pid_is_alive(pid)),
            "pid": pid,
            "heartbeat_age_seconds": heartbeat_age,
            "heartbeat": heartbeat_data,
            "lockfile": str(self.lockfile),
        }

    def close(self):
        self.running = False
        self._cleanup_pidfile()
        if self._lock_handle is not None:
            try:
                fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_UN)
            finally:
                self._lock_handle.close()
                self._lock_handle = None


def rotate_logs(
    log_dir: Path = LOG_DIR,
    max_size_mb: int = 50,
    retention_days: int = 30,
) -> list[str]:
    rotated = []
    log_dir = Path(log_dir)
    if not log_dir.exists():
        return rotated

    now_ts = _utcnow().timestamp()
    retention_seconds = max(0, retention_days) * 86400

    for path in sorted(log_dir.glob("*.jsonl")):
        if path.stat().st_size > max_size_mb * 1024 * 1024:
            archive = path.with_suffix(
                f".jsonl.{_utcnow().strftime('%Y%m%d_%H%M%S')}.gz"
            )
            with open(path, "rb") as src, gzip.open(archive, "wb") as dst:
                dst.write(src.read())
            path.unlink()
            rotated.append(str(archive))

    if retention_seconds:
        for archive in log_dir.glob("*.jsonl.*.gz"):
            if now_ts - archive.stat().st_mtime > retention_seconds:
                archive.unlink(missing_ok=True)

    return rotated
