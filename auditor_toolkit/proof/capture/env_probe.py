"""Probe browser environment for reproducible capture configuration.

Detects viewport dimensions, fonts, user-agent, and browser version
so that every before/after capture uses identical settings.
"""

from __future__ import annotations

from datetime import datetime
from datetime import timezone as tz_utc

from auditor_toolkit.proof.schema import CaptureEnvironment


def probe_environment(
    viewport_width: int = 1280,
    viewport_height: int = 900,
    device_scale_factor: float = 1.0,
    browser_type: str = "chromium",
    locale: str = "en-NZ",
    timezone: str = "Pacific/Auckland",
    user_agent: str = "",
    fonts: list[str] | None = None,
) -> CaptureEnvironment:
    """Return a pinned CaptureEnvironment with the given parameters.

    When *user_agent* is empty the caller is expected to supply it from a
    live browser probe or leave it blank for headless defaults.

    *fonts* defaults to an empty list when not provided so the environment
    fingerprint stays stable across probes.
    """
    return CaptureEnvironment(
        viewport_width=viewport_width,
        viewport_height=viewport_height,
        device_scale_factor=device_scale_factor,
        user_agent=user_agent,
        browser_type=browser_type,
        locale=locale,
        timezone=timezone,
        fonts=fonts or [],
        timestamp=datetime.now(tz_utc.utc).isoformat(),
    )
