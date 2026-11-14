
"""Configuration hot-reload watcher for routing.yaml."""
import json
import yaml
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
            config = yaml.safe_load(config_text) if self.config_path.suffix in {'.yaml', '.yml'} else json.loads(config_text)

            if not isinstance(config, dict):
                return False

            # Accept either the historical PURPOSE_ROUTES shape or the current
            # role-based zero-cost routing.yaml. Validation must never trigger
            # model/network probes.
            if 'PURPOSE_ROUTES' in config:
                routes = config['PURPOSE_ROUTES']
                if not isinstance(routes, dict) or not routes:
                    return False
            else:
                policy = config.get('policy') or {}
                roles = config.get('roles') or {}
                if policy.get('paid_tokens') is not False or not roles:
                    return False
                if policy.get('max_price') != {
                    'prompt': 0, 'completion': 0, 'request': 0, 'image': 0
                }:
                    return False

            self._last_known_good = config
            return True

        except Exception:
            return False

    def get_last_known_good(self):
        return self._last_known_good.copy() if self._last_known_good else None

    def is_running(self):
        return self._running
