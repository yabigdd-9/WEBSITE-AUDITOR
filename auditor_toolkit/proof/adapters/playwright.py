"""Playwright browser adapter for proof captures.

Provides functions to create a proof-consistent browser context, capture
before/after states, and block external network requests during proof
generation.
"""

from __future__ import annotations

from typing import Any

try:
    from playwright.sync_api import Route, sync_playwright  # BrowserContext used via type hint
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from auditor_toolkit.proof.environment import ProofEnvironment


def create_proof_browser_context(
    env: ProofEnvironment | None = None,
) -> tuple[Any, Any, Any]:
    """Launch a headless browser and return (playwright, browser, context).

    The context uses the exact viewport, locale, timezone, and device scale
    factor from *env* to ensure before/after comparability.
    Caller must close all three objects when done.

    Returns (None, None, None) when Playwright is not available.
    """
    if not HAS_PLAYWRIGHT:
        return None, None, None

    if env is None:
        from auditor_toolkit.proof.environment import probe_environment
        env = probe_environment()

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": env.viewport_width, "height": env.viewport_height},
        device_scale_factor=env.device_scale_factor,
        locale=env.locale,
        timezone_id=env.timezone,
        reduced_motion=env.reduced_motion,
        color_scheme=env.color_scheme,
    )
    return pw, browser, context


def capture_before_state(
    page: Any,
    finding: dict[str, Any],
    timeout: int = 30_000,
) -> dict[str, Any]:
    """Navigate to the finding URL and capture the pre-fix state.

    Returns a dict with url, outer_html, bounding_box, and console_errors.
    """
    url = finding.get("url", "")
    selector = finding.get("selector", "")

    console_errors: list[str] = []

    def _on_console(msg: Any) -> None:
        if msg.type == "error":
            console_errors.append(msg.text)

    page.on("console", _on_console)
    page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    page.wait_for_timeout(2000)

    outer_html = ""
    bounding_box: dict[str, int] = {}

    if selector:
        try:
            el = page.wait_for_selector(selector, timeout=5000)
            if el is not None:
                outer_html = el.evaluate("el => el.outerHTML")[:4000]
                box = el.bounding_box()
                if box:
                    bounding_box = {
                        "x": int(box["x"]),
                        "y": int(box["y"]),
                        "width": int(box["width"]),
                        "height": int(box["height"]),
                    }
        except Exception:
            pass

    return {
        "url": page.url,
        "outer_html": outer_html,
        "bounding_box": bounding_box,
        "console_errors": console_errors,
    }


def capture_after_state(
    page: Any,
    prototype: Any,
    timeout: int = 30_000,
) -> dict[str, Any]:
    """Navigate to the prototype URL and capture the post-fix state.

    *prototype* may be a Prototype object (with assets_dir) or a plain
    dict with a "url" key pointing to a locally served prototype.
    """
    url = getattr(prototype, "url", "") if hasattr(prototype, "url") else prototype.get("url", "")
    if not url and hasattr(prototype, "assets_dir"):
        url = f"file://{prototype.assets_dir}/index.html"

    console_errors: list[str] = []

    def _on_console(msg: Any) -> None:
        if msg.type == "error":
            console_errors.append(msg.text)

    page.on("console", _on_console)
    page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    page.wait_for_timeout(2000)

    return {
        "url": page.url,
        "outer_html": page.content()[:4000],
        "console_errors": console_errors,
    }


def route_block_external(route: Route) -> None:
    """Playwright route handler that blocks all external network requests.

    Only allows requests to localhost, file://, and data: URIs.
    Aborts everything else to ensure a fully sandboxed proof capture.
    """
    url = route.request.url
    blocked_methods = {"POST", "PUT", "PATCH", "DELETE"}

    if route.request.method.upper() in blocked_methods:
        route.abort()
        return

    allowed_prefixes = ("http://localhost", "http://127.0.0.1", "file://", "data:")
    if not any(url.startswith(prefix) for prefix in allowed_prefixes):
        route.abort()
        return

    route.continue_()
