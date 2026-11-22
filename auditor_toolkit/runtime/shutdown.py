"""Graceful shutdown — stop accepting, finish safe jobs, checkpoint, exit."""

from __future__ import annotations

import signal
import threading
from typing import Any, Callable

_shutdown_event = threading.Event()
_shutdown_callbacks: list[Callable[[], None]] = []


def request_shutdown(signum: int = 0, frame: Any = None) -> None:
    """Signal handler for SIGTERM/SIGINT."""
    _shutdown_event.set()


def register_shutdown_callback(callback: Callable[[], None]) -> None:
    """Register a callback to run during graceful shutdown."""
    _shutdown_callbacks.append(callback)


def is_shutting_down() -> bool:
    return _shutdown_event.is_set()


def install_signal_handlers() -> None:
    """Install SIGTERM/SIGINT handlers."""
    signal.signal(signal.SIGTERM, request_shutdown)
    try:
        signal.signal(signal.SIGINT, request_shutdown)
    except ValueError:
        pass  # Not in main thread


def execute_shutdown() -> None:
    """Execute all registered shutdown callbacks."""
    _shutdown_event.set()
    for cb in _shutdown_callbacks:
        try:
            cb()
        except Exception:
            pass
