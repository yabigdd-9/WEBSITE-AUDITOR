"""Worker hot-reload for mm_workers.py changes."""
import importlib
import threading
import time
from pathlib import Path
from typing import Dict, Any

from mm_pipeline import Worker
from mm_pipeline import log


class WorkerHotReloader:
    """Watches mm_workers.py for changes and hot-reloads workers."""

    def __init__(self, workers_module):
        self.workers_module = workers_module
        self._lock = threading.Lock()
        self._running = False
        self._last_mtime = 0
        self._thread = None

    def start(self, poll_interval: float = 5.0):
        """Start watching for changes."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, args=(poll_interval,), daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _watch_loop(self, poll_interval: float):
        workers_path = Path(__file__).parent.parent / 'mm_workers.py'
        while self._running:
            try:
                mtime = workers_path.stat().st_mtime
                if mtime > self._last_mtime:
                    self._last_mtime = mtime
                    self._reload()
            except Exception as e:
                log({'kind': 'hotreload_error', 'error': str(e)})
            time.sleep(poll_interval)

    def _reload(self):
        with self._lock:
            try:
                import mm_workers
                importlib.reload(mm_workers)
                from mm_workers import WORKERS
                # Notify running workers to reload
                log({'kind': 'hotreload', 'workers': list(WORKERS.keys())})
            except Exception as e:
                from mm_pipeline import log
                log({'kind': 'hotreload_failed', 'error': str(e)})

def create_hot_reloader(workers_module):
    return WorkerHotReloader(workers_module)
