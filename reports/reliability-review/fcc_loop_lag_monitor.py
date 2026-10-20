"""Event-loop scheduling-lag monitor with live frame capture.

Two components:

* an async task that times a 10 ms timer, measuring how long the loop is
  prevented from scheduling it (scheduling lag);
* a plain OS thread that watches that heartbeat and, when the loop stops
  ticking, dumps ``sys._current_frames()`` for the loop thread. That captures
  the exact frame the loop is blocked in, without py-spy (which needs root on
  macOS) and without an async task (which cannot run while the loop is blocked).

Writes JSONL: {"t","lag_ms","gc","blockers"} and, on capture,
{"t","capture":true,"frames":[...]}.
"""

from __future__ import annotations

import asyncio
import gc
import json
import sys
import threading
import time
import traceback
from pathlib import Path


class LoopLagMonitor:
    def __init__(
        self,
        path: str | Path,
        *,
        interval: float = 0.01,
        threshold: float = 0.05,
        stacks: bool = True,
        capture_after: float = 0.25,
    ) -> None:
        self._path = Path(path)
        self._interval = interval
        self._threshold = threshold
        self._stacks = stacks
        self._capture_after = capture_after
        self._handle = self._path.open("a", encoding="utf-8")
        self._lock = threading.Lock()
        self._beat = time.monotonic()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._captures = 0
        self.samples = 0
        self.stalls = 0
        self.max_lag = 0.0

    # ------------------------------------------------------------------ io
    def _write(self, record: dict) -> None:
        with self._lock:
            self._handle.write(json.dumps(record) + "\n")
            self._handle.flush()

    # ----------------------------------------------------------- heartbeat
    def _gc_state(self) -> dict:
        try:
            stats = gc.get_stats()
        except Exception:  # pragma: no cover - defensive
            return {}
        return {
            "count": list(gc.get_count()),
            "gen": [
                {"collections": s.get("collections"), "collected": s.get("collected")}
                for s in stats
            ],
        }

    def _blockers(self) -> list[dict]:
        out: list[dict] = []
        for task in asyncio.all_tasks():
            try:
                stack = task.get_stack()
            except Exception:  # pragma: no cover - defensive
                continue
            if not stack:
                continue
            out.append(
                {
                    "task": task.get_name(),
                    "frames": [
                        f"{Path(f.f_code.co_filename).name}:{f.f_lineno} {f.f_code.co_name}"
                        for f in stack[-4:]
                    ],
                }
            )
        return out

    async def run(self) -> None:
        loop_thread = threading.get_ident()
        self._thread = threading.Thread(
            target=self._watch, args=(loop_thread,), name="loop-lag-watchdog", daemon=True
        )
        self._thread.start()

        while not self._stop.is_set():
            started = time.perf_counter()
            await asyncio.sleep(self._interval)
            lag = time.perf_counter() - started - self._interval
            self._beat = time.monotonic()
            self.samples += 1
            self.max_lag = max(self.max_lag, lag)
            record: dict = {
                "t": time.time(),
                "lag_ms": round(lag * 1000, 3),
                "gc": self._gc_state(),
            }
            if lag >= self._threshold:
                self.stalls += 1
                record["stall"] = True
                if self._stacks:
                    record["blockers"] = self._blockers()
            self._write(record)

    # -------------------------------------------------------------- watchdog
    def _watch(self, loop_thread: int) -> None:
        """Dump the loop thread's live stack whenever the heartbeat stops."""

        while not self._stop.is_set():
            time.sleep(0.05)
            silence = time.monotonic() - self._beat
            if silence < self._capture_after:
                continue
            frames = sys._current_frames().get(loop_thread)
            if frames is None:
                continue
            captured = [
                f"{Path(f.filename).name}:{f.lineno} {f.name}"
                for f in traceback.extract_stack(frames)
            ]
            self._captures += 1
            self._write(
                {
                    "t": time.time(),
                    "capture": True,
                    "silence_s": round(silence, 3),
                    "frames": captured[-18:],
                }
            )
            # One capture per stall; wait for the loop to resume.
            while time.monotonic() - self._beat < 0.05 and not self._stop.is_set():
                time.sleep(0.05)

    def close(self) -> None:
        self._stop.set()
        try:
            self._handle.close()
        except Exception:  # pragma: no cover - defensive
            pass


def install(path: str, *, threshold: float = 0.05) -> asyncio.Task:
    """Start the monitor on the running loop and return its task."""

    monitor = LoopLagMonitor(path, threshold=threshold)
    task = asyncio.get_running_loop().create_task(monitor.run(), name="loop-lag-monitor")
    task.monitor = monitor  # type: ignore[attr-defined]
    return task


__all__ = ["LoopLagMonitor", "install"]
