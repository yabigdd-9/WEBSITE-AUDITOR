"""Pinned Playwright browser capture for before/after proof.

Captures screenshot, DOM, console errors, and network requests with a
fixed viewport (1280x900), locale (en-NZ), and timezone (Pacific/Auckland).
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from datetime import datetime, timezone
from typing import Any

from playwright.sync_api import (
    ConsoleMessage,
    Response,
    sync_playwright,
)

from auditor_toolkit.proof.capture.env_probe import probe_environment
from auditor_toolkit.proof.schema import (
    AfterState,
    BeforeState,
    CaptureEnvironment,
    DOMSnapshot,
    IssueRegion,
    ScreenshotArtifact,
)

# Default pinned settings
_DEFAULT_VIEWPORT = {"width": 1280, "height": 900}
_DEFAULT_LOCALE = "en-NZ"
_DEFAULT_TIMEZONE = "Pacific/Auckland"
_DEFAULT_BROWSER = "chromium"
_default_output_dir = tempfile.mkdtemp(prefix="website-auditor-proof-")


def _sha256(path: str) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _collect_console_errors(page: Any) -> list[str]:
    """Collect console error messages from a page."""
    errors: list[str] = []

    def _on_console(msg: ConsoleMessage) -> None:
        if msg.type in ("error",):
            errors.append(msg.text)

    page.on("console", _on_console)
    return errors


def _collect_network_requests(page: Any) -> list[dict[str, Any]]:
    """Collect failed network requests from a page."""
    requests: list[dict[str, Any]] = []

    def _on_response(response: Response) -> None:
        if response.status >= 400:
            requests.append({
                "url": response.url,
                "status": response.status,
                "method": response.request.method,
            })

    page.on("response", _on_response)
    return requests


def _save_screenshot(page: Any, output_dir: str, label: str) -> ScreenshotArtifact:
    """Take a full-page screenshot and return a ScreenshotArtifact."""
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(output_dir, f"{label}_{ts}.png")
    page.screenshot(path=path, full_page=True)
    viewport = page.viewport_size or {}
    vp_str = f"{viewport.get('width', '?')}x{viewport.get('height', '?')}"
    return ScreenshotArtifact(
        path=path,
        url=page.url,
        viewport=vp_str,
        timestamp=ts,
        sha256=_sha256(path),
        size_bytes=os.path.getsize(path),
    )


def _save_dom_snapshot(page: Any, output_dir: str, label: str) -> DOMSnapshot:
    """Save the full page HTML and return a DOMSnapshot."""
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    html_path = os.path.join(output_dir, f"{label}_{ts}.html")
    html = page.content()
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    return DOMSnapshot(
        html_path=html_path,
        url=page.url,
        timestamp=ts,
        sha256=_sha256(html_path),
    )


def capture_before(
    url: str,
    output_dir: str = _default_output_dir,
    timeout: int = 30_000,
    issue_region: IssueRegion | None = None,
    env: CaptureEnvironment | None = None,
) -> BeforeState:
    """Capture the full before state of a URL using pinned browser settings.

    Returns a BeforeState with screenshot, DOM, console errors, network
    requests, and environment fingerprint.
    """
    if env is None:
        env = probe_environment()

    console_errors: list[str] = []
    network_requests: list[dict[str, Any]] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport=_DEFAULT_VIEWPORT,
            locale=_DEFAULT_LOCALE,
            timezone_id=_DEFAULT_TIMEZONE,
            device_scale_factor=env.device_scale_factor,
        )
        page = context.new_page()

        # Attach collectors before navigation
        _collect_console_errors(page)  # noqa: F841
        _collect_network_requests(page)  # noqa: F841

        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        # Allow additional time for lazy resources
        page.wait_for_timeout(2000)

        screenshot = _save_screenshot(page, output_dir, "before")
        dom = _save_dom_snapshot(page, output_dir, "before")

        # Resolve the issue region if a selector was provided
        resolved_region = issue_region or IssueRegion(
            finding_id="",
            selector="",
        )

        if issue_region and issue_region.selector:
            try:
                element = page.wait_for_selector(
                    issue_region.selector, timeout=5000
                )
                if element is not None:
                    box = element.bounding_box()
                    if box:
                        resolved_region = IssueRegion(
                            finding_id=issue_region.finding_id,
                            selector=issue_region.selector,
                            outer_html_snippet=element.evaluate(
                                "el => el.outerHTML"
                            )[:2000],
                            bounding_box={
                                "x": int(box["x"]),
                                "y": int(box["y"]),
                                "width": int(box["width"]),
                                "height": int(box["height"]),
                            },
                            description=issue_region.description,
                            severity=issue_region.severity,
                        )
            except Exception:
                # Selector not found — leave region with minimal info
                pass

        browser.close()

    return BeforeState(
        finding_id=issue_region.finding_id if issue_region else "",
        url=url,
        capture_env=env,
        screenshot=screenshot,
        dom_snapshot=dom,
        issue_region=resolved_region,
        console_errors=console_errors,
        network_requests=network_requests,
        status="CAPTURED",
        captured_at=datetime.now(timezone.utc).isoformat(),
    )


def capture_after(
    url: str,
    finding_id: str,
    proposed_fix_id: str,
    output_dir: str = _default_output_dir,
    timeout: int = 30_000,
    issue_region: IssueRegion | None = None,
    env: CaptureEnvironment | None = None,
) -> AfterState:
    """Capture the full after state of a URL with a fix applied.

    Uses identical browser settings as capture_before for valid comparison.
    """
    if env is None:
        env = probe_environment()

    console_errors: list[str] = []
    network_requests: list[dict[str, Any]] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport=_DEFAULT_VIEWPORT,
            locale=_DEFAULT_LOCALE,
            timezone_id=_DEFAULT_TIMEZONE,
            device_scale_factor=env.device_scale_factor,
        )
        page = context.new_page()

        _collect_console_errors(page)  # noqa: F841
        _collect_network_requests(page)  # noqa: F841

        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        page.wait_for_timeout(2000)

        screenshot = _save_screenshot(page, output_dir, "after")
        dom = _save_dom_snapshot(page, output_dir, "after")

        resolved_region = issue_region or IssueRegion(
            finding_id=finding_id,
            selector="",
        )

        browser.close()

    return AfterState(
        finding_id=finding_id,
        proposed_fix_id=proposed_fix_id,
        url=url,
        capture_env=env,
        screenshot=screenshot,
        dom_snapshot=dom,
        issue_region=resolved_region,
        console_errors=console_errors,
        network_requests=network_requests,
        status="CAPTURED",
        captured_at=datetime.now(timezone.utc).isoformat(),
    )
