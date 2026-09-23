"""Extract issue region from a live page using a CSS selector.

Returns an IssueRegion with the outerHTML snippet and bounding box for
the element matching the selector from a verified finding.
"""

from __future__ import annotations

from playwright.sync_api import sync_playwright

from auditor_toolkit.proof.schema import IssueRegion

_DEFAULT_VIEWPORT = {"width": 1280, "height": 900}
_DEFAULT_LOCALE = "en-NZ"
_DEFAULT_TIMEZONE = "Pacific/Auckland"


def extract_issue_region(
    url: str,
    finding_id: str,
    selector: str,
    description: str = "",
    severity: str = "",
    timeout: int = 15_000,
) -> IssueRegion:
    """Navigate to *url* and extract the element matching *selector*.

    Returns an IssueRegion populated with the element's outerHTML (truncated
    to 2000 chars) and its bounding box coordinates.
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport=_DEFAULT_VIEWPORT,
            locale=_DEFAULT_LOCALE,
            timezone_id=_DEFAULT_TIMEZONE,
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            element = page.wait_for_selector(selector, timeout=5000)

            if element is None:
                return IssueRegion(
                    finding_id=finding_id,
                    selector=selector,
                    description=description or "Element not found",
                    severity=severity,
                )

            outer_html = element.evaluate("el => el.outerHTML")[:2000]
            box = element.bounding_box()

            bounding_box = {}
            if box:
                bounding_box = {
                    "x": int(box["x"]),
                    "y": int(box["y"]),
                    "width": int(box["width"]),
                    "height": int(box["height"]),
                }

            return IssueRegion(
                finding_id=finding_id,
                selector=selector,
                outer_html_snippet=outer_html,
                bounding_box=bounding_box,
                description=description,
                severity=severity,
            )
        finally:
            browser.close()
