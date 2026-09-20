#!/usr/bin/env python3
"""SupervisorDaemon — PID-lock, graceful shutdown, heartbeat, log rotation."""

import os, signal, time, json, gzip
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
PIDFILE = ROOT / "state" / "supervisor.pid"
HEARTBEAT = ROOT / "state" / "supervisor.heartbeat"
LOG_DIR = ROOT / "state" / "worker-logs"

class SupervisorDaemon:
    def __init__(self, pidfile: Path = PIDFILE, heartbeat: Path = HEARTBEAT):
        self.pidfile = pidfile
        self.heartbeat = heartbeat
        self.running = True
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        signal.signal(signal.SIGTERM, self._on_stop)
        signal.signal(signal.SIGINT, self._on_stop)

    def _on_stop(self, signum, frame):
        self.running = False
        self.pidfile.unlink(missing_ok=True)

    def start(self) -> bool:
        if self.pidfile.exists():
            try:
                other_pid = int(self.pidfile.read_text().strip())
                if Path(f"/proc/{other_pid}").exists():
                    return False  # dual-start blocked
            except Exception:
                pass
        self.pidfile.write_text(str(os.getpid()))
        self.heartbeat.write_text(json.dumps({"pid": os.getpid(), "started": datetime.now(timezone.utc).isoformat()}))
        return True

    def tick(self) -> dict:
        if not self.running:
            return {"stopped": True}
        self.heartbeat.write_text(json.dumps({"pid": os.getpid(), "last_tick": datetime.now(timezone.utc).isoformat()}))
        return {"running": True, "pid": os.getpid(), "heartbeat": str(self.heartbeat)}

    def status(self) -> dict:
        return {
            "pidfile_exists": self.pidfile.exists(),
            "heartbeat_exists": self.heartbeat.exists(),
            "running": self.running,
            "pid": int(self.pidfile.read_text().strip()) if self.pidfile.exists() else None,
        }

def rotate_logs(log_dir: Path = LOG_DIR, max_size_mb: int = 50, retention_days: int = 30) -> list[str]:
    rotated = []
    if not log_dir.exists():
        return rotated
    for f in sorted(log_dir.glob("*.jsonl")):
        if f.stat().st_size > max_size_mb * 1024 * 1024:
            archive = f.with_suffix(f".jsonl.{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.gz")
            with open(f, 'rb') as src, gzip.open(archive, 'wb') as dst:
                dst.write(src.read())
            f.unlink()
            rotated.append(str(archive))
    return rotated
