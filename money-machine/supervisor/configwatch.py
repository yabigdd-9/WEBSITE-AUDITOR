
"""Configuration hot-reload watcher for routing.yaml."""
import json
import threading
import time
from pathlib import Path
from typing import Optional, Callable, Dict, Any

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False

from mm_model_router import probe_llamacpp
from mm_pipeline import log


class ConfigChangeHandler(FileSystemEventHandler):
    """Handles file system events for config files."""

    def __init__(self, config_path: Path, callback):
        self.config_path = config_path.resolve()
        self.callback = callback
        self._last_mtime = 0

    def on_modified(self, event):
        if event.is_directory:
            return
        if Path(event.src_path).resolve() == self.config_path:
            now = time.time()
            if now - self._last_mtime < 0.5:
                return
            self._last_mtime = now
            self.callback()


class ConfigWatcher:
    """Watches configuration files for changes and triggers hot-reload."""

    def __init__(
        self,
        config_path: Path,
        on_reload = None,
        validate_on_change: bool = True,
    ):
        self.config_path = Path(config_path).resolve()
        self.on_reload = on_reload
        self.validate_on_change = validate_on_change

        self._observer = None
        self._running = False
        self._last_known_good = None
        self._lock = threading.Lock()

        self._observer = None

    def start(self) -> bool:
        if not self.config_path.exists():
            return False

        with self._lock:
            if self._running:
                return True

            if self._validate_and_cache():
                self._running = True
                return True
            return False

    def stop(self) -> None:
        with self._lock:
            if self._observer and self._running:
                self._observer.stop()
                self._observer.join(timeout=5)
                self._running = False

    def _validate_and_cache(self) -> bool:
        try:
            config_text = self.config_path.read_text()
            config = json.loads(config_text)

            if 'PURPOSE_ROUTES' not in config:
                return False

            for role, routes in config['PURPOSE_ROUTES'].items():
                for provider, model in routes:
                    if provider.startswith('local:'):
                        kind = provider.split(':', 1)[1]
                        if kind == 'llamacpp':
                            from mm_model_router import probe_llamacpp
                            probe_llamacpp()

            with open(self.config_path) as f:
                self._last_known_good = json.load(f)

            return True

        except Exception:
            return False

    def get_last_known_good(self):
        return self._last_known_good.copy() if self._last_known_good else None

    def is_running(self):
        return self._running
