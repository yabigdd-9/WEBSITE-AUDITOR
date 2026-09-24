"""Capture sub-package — environment probing with lazy browser capture exports."""

from __future__ import annotations

from typing import Any

from .env_probe import CaptureEnvironment, probe_environment


def capture_before(*args: Any, **kwargs: Any) -> Any:
    """Lazy-load Playwright only when an actual browser capture is requested."""
    from .browser_capture import capture_before as _capture_before

    return _capture_before(*args, **kwargs)


def capture_after(*args: Any, **kwargs: Any) -> Any:
    """Lazy-load Playwright only when an actual browser capture is requested."""
    from .browser_capture import capture_after as _capture_after

    return _capture_after(*args, **kwargs)


__all__ = [
    "capture_before",
    "capture_after",
    "probe_environment",
    "CaptureEnvironment",
]
