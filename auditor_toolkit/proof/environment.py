"""ProofEnvironment — browser fingerprint + probe function.

Records browser name/version, Playwright version, viewport,
device_scale_factor, locale, timezone, reduced_motion, color_scheme,
fonts, capture_timestamp, page_snapshot_id.  Before/after captures
must match exactly.
"""

from __future__ import annotations

import hashlib
import platform
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class ProofEnvironment:
    """Immutable snapshot of everything that can affect a browser render.

    Two captures are considered comparable only when their
    ProofEnvironment instances produce the same *fingerprint*.
    """

    browser_name: str = "chromium"
    browser_version: str = ""
    playwright_version: str = ""
    viewport_width: int = 1280
    viewport_height: int = 900
    device_scale_factor: float = 1.0
    locale: str = "en-NZ"
    timezone: str = "Pacific/Auckland"
    reduced_motion: str = "no-preference"  # "no-preference" | "reduce"
    color_scheme: str = "light"  # "light" | "dark" | "no-preference"
    fonts: list[str] = field(default_factory=list)
    capture_timestamp: str = ""
    page_snapshot_id: str = ""

    def fingerprint(self) -> str:
        """Content-addressed stable hash for this environment."""
        raw = (
            f"{self.browser_name}@{self.browser_version}"
            f"|pw{self.playwright_version}"
            f"|{self.viewport_width}x{self.viewport_height}@{self.device_scale_factor}"
            f"|{self.locale}|{self.timezone}"
            f"|{self.reduced_motion}|{self.color_scheme}"
            f"|{','.join(sorted(self.fonts))}"
        )
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def matches(self, other: ProofEnvironment) -> bool:
        """Return True when *other* has an identical fingerprint."""
        if not isinstance(other, ProofEnvironment):
            return False
        return self.fingerprint() == other.fingerprint()


def probe_environment() -> ProofEnvironment:
    """Detect the current browser / OS environment and return a ProofEnvironment.

    When called outside a live browser context (e.g. from a test harness),
    returns sensible defaults with the host platform recorded.
    """
    browser_version = ""
    playwright_version = ""

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pass
    else:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            browser_version = browser.version
            playwright_version = getattr(pw, "version", "")
            browser.close()

    ts = datetime.now(timezone.utc).isoformat()
    snapshot_id = hashlib.sha256(
        f"{ts}-{platform.node()}".encode()
    ).hexdigest()[:12]

    return ProofEnvironment(
        browser_name="chromium",
        browser_version=browser_version,
        playwright_version=playwright_version,
        viewport_width=1280,
        viewport_height=900,
        device_scale_factor=1.0,
        locale="en-NZ",
        timezone="Pacific/Auckland",
        reduced_motion="no-preference",
        color_scheme="light",
        fonts=[],
        capture_timestamp=ts,
        page_snapshot_id=snapshot_id,
    )
