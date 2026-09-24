"""Issue region extraction from verified findings.

Given a finding (with selector, bounding_box), extracts the target element
with configurable context padding.  Fallback chain:
  selector → role/name → DOM similarity → bounding_box → NEEDS_REVIEW
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

RegionCaptureStatus = Literal[
    "CAPTURED",
    "PARTIAL",
    "TARGET_NOT_FOUND",
    "NEEDS_REVIEW",
]


@dataclass(frozen=True)
class IssueRegion:
    """Extracted issue region with outer HTML and bounding box.

    *capture_status* records how confidently the target was located:
    CAPTURED / PARTIAL / TARGET_NOT_FOUND / NEEDS_REVIEW.
    """

    finding_id: str = ""
    selector: str = ""
    outer_html: str = ""
    bounding_box: dict[str, int] = field(default_factory=dict)
    capture_status: RegionCaptureStatus = "NEEDS_REVIEW"
    description: str = ""
    severity: str = ""


# Default padding around the target element
_DEFAULT_HORIZONTAL_PAD = 80
_DEFAULT_VERTICAL_PAD = 100


def _pad_bounding_box(
    box: dict[str, int],
    horizontal_padding_px: int = _DEFAULT_HORIZONTAL_PAD,
    vertical_padding_px: int = _DEFAULT_VERTICAL_PAD,
    page_width: int = 1280,
    page_height: int = 900,
) -> dict[str, int]:
    """Expand *box* by the given padding, clamped to page boundaries."""
    x = max(0, box.get("x", 0) - horizontal_padding_px)
    y = max(0, box.get("y", 0) - vertical_padding_px)
    w = min(
        page_width - x,
        box.get("width", 0) + 2 * horizontal_padding_px,
    )
    h = min(
        page_height - y,
        box.get("height", 0) + 2 * vertical_padding_px,
    )
    return {"x": x, "y": y, "width": w, "height": h}


def _by_selector(page: Any, selector: str) -> tuple[Any | None, str, dict[str, int]]:
    """Try locating the element via CSS selector."""
    try:
        el = page.wait_for_selector(selector, timeout=5000)
        if el is None:
            return None, "", {}
        outer = el.evaluate("el => el.outerHTML")[:4000]
        box = el.bounding_box()
        if box:
            return el, outer, {
                "x": int(box["x"]),
                "y": int(box["y"]),
                "width": int(box["width"]),
                "height": int(box["height"]),
            }
        return el, outer, {}
    except Exception:
        return None, "", {}


def _by_role_name(page: Any, finding: dict[str, Any]) -> tuple[Any | None, str, dict[str, int]]:
    """Fallback: locate by ARIA role + accessible name."""
    role = finding.get("role") or finding.get("aria_role", "")
    name = finding.get("accessible_name") or finding.get("name", "")
    if not role:
        return None, "", {}
    try:
        selector = f'[role="{role}"]'
        elements = page.query_selector_all(selector)
        for el in elements:
            el_name = el.evaluate(
                "el => el.getAttribute('aria-label') || el.textContent?.trim().slice(0, 100) || ''"
            )
            if name.lower() in el_name.lower():
                outer = el.evaluate("el => el.outerHTML")[:4000]
                box = el.bounding_box()
                bb = {}
                if box:
                    bb = {
                        "x": int(box["x"]),
                        "y": int(box["y"]),
                        "width": int(box["width"]),
                        "height": int(box["height"]),
                    }
                return el, outer, bb
    except Exception:
        pass
    return None, "", {}


def _by_bounding_box(page: Any, bb: dict[str, int]) -> tuple[Any | None, str, dict[str, int]]:
    """Fallback: element at center of bounding box via JS."""
    if not bb:
        return None, "", {}
    cx = bb.get("x", 0) + bb.get("width", 0) // 2
    cy = bb.get("y", 0) + bb.get("height", 0) // 2
    try:
        el = page.evaluate(
            """(args) => {
                const el = document.elementFromPoint(args.x, args.y);
                return el ? el.outerHTML : null;
            }""",
            {"x": cx, "y": cy},
        )
        if el:
            return None, str(el), bb
    except Exception:
        pass
    return None, "", bb


def extract_issue_region(
    page: Any,
    finding: dict[str, Any],
    horizontal_padding_px: int = _DEFAULT_HORIZONTAL_PAD,
    vertical_padding_px: int = _DEFAULT_VERTICAL_PAD,
) -> IssueRegion:
    """Extract the issue region for *finding* from a live *page*.

    Fallback chain:
      1. CSS selector (from finding["selector"] or finding["evidence"])
      2. role/name (ARIA)
      3. bounding_box from evidence
      4. NEEDS_REVIEW
    """
    finding_id = finding.get("finding_id", "")
    selector = finding.get("selector", "")
    if not selector:
        selector = _evidence_selector(finding)

    region = _region_by_selector(page, finding, selector)
    if region is not None:
        return region

    region = _region_by_role(page, finding)
    if region is not None:
        return region

    return _region_by_evidence_box(page, finding) or IssueRegion(
        finding_id=finding_id,
        description=finding.get("claim", ""),
        severity=finding.get("severity", ""),
    )


def _evidence_selector(finding: dict[str, Any]) -> str:
    return next(
        (evidence.get("selector", "") for evidence in finding.get("evidence", [])
         if evidence.get("selector")),
        "",
    )


def _region_by_selector(page: Any, finding: dict[str, Any], selector: str) -> IssueRegion | None:
    if not selector:
        return None
    element, outer, box = _by_selector(page, selector)
    if element is None and not outer:
        return None
    return _region_from_capture(finding, selector, outer, box)


def _region_by_role(page: Any, finding: dict[str, Any]) -> IssueRegion | None:
    element, outer, box = _by_role_name(page, finding)
    if element is None and not outer:
        return None
    return _region_from_capture(finding, "", outer, box)


def _region_from_capture(
    finding: dict[str, Any],
    selector: str,
    outer: str,
    box: dict[str, int],
) -> IssueRegion:
    return IssueRegion(
        finding_id=finding.get("finding_id", ""),
        selector=selector,
        outer_html=outer,
        bounding_box=_pad_bounding_box(box) if box else {},
        capture_status="CAPTURED" if box else "PARTIAL",
        description=finding.get("claim", ""),
        severity=finding.get("severity", ""),
    )


def _region_by_evidence_box(page: Any, finding: dict[str, Any]) -> IssueRegion | None:
    box = next(
        (evidence.get("bounding_box", {}) for evidence in finding.get("evidence", [])
         if evidence.get("bounding_box")),
        {},
    )
    if not box:
        return None
    _, outer, _ = _by_bounding_box(page, box)
    return IssueRegion(
        finding_id=finding.get("finding_id", ""),
        outer_html=outer,
        bounding_box=_pad_bounding_box(box),
        capture_status="CAPTURED" if outer else "TARGET_NOT_FOUND",
        description=finding.get("claim", ""),
        severity=finding.get("severity", ""),
    )
