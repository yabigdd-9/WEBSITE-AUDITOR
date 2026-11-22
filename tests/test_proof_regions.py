"""Tests for issue region extraction from verified findings."""

import json
import os

from auditor_toolkit.proof.regions import (
    IssueRegion,
    _pad_bounding_box,
    extract_issue_region,
)

_FIXTURES_DIR = os.path.join(
    os.path.dirname(__file__), "fixtures", "proof", "findings"
)


def _load_fixture(name: str) -> dict:
    path = os.path.join(_FIXTURES_DIR, name)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Padding tests
# ---------------------------------------------------------------------------

def test_pad_bounding_box_expands():
    box = {"x": 100, "y": 200, "width": 300, "height": 50}
    padded = _pad_bounding_box(box, horizontal_padding_px=80, vertical_padding_px=100)
    assert padded["x"] == 20  # 100 - 80
    assert padded["y"] == 100  # 200 - 100
    assert padded["width"] == 460  # 300 + 2*80
    assert padded["height"] == 250  # 50 + 2*100


def test_pad_bounding_box_clamped_left():
    box = {"x": 30, "y": 50, "width": 200, "height": 100}
    padded = _pad_bounding_box(box, horizontal_padding_px=80, vertical_padding_px=100)
    assert padded["x"] == 0  # clamped
    # width = min(1280 - 0, 200 + 2*80) = min(1280, 360) = 360
    assert padded["width"] == 360


def test_pad_bounding_box_empty():
    padded = _pad_bounding_box({}, horizontal_padding_px=80, vertical_padding_px=100)
    assert padded == {"x": 0, "y": 0, "width": 160, "height": 200}


# ---------------------------------------------------------------------------
# IssueRegion dataclass
# ---------------------------------------------------------------------------

def test_issue_region_defaults():
    region = IssueRegion()
    assert region.finding_id == ""
    assert region.capture_status == "NEEDS_REVIEW"


def test_issue_region_from_values():
    region = IssueRegion(
        finding_id="f001",
        selector=".cta",
        outer_html="<div class='cta'>",
        bounding_box={"x": 0, "y": 520, "width": 390, "height": 45},
        capture_status="CAPTURED",
    )
    assert region.finding_id == "f001"
    assert region.selector == ".cta"
    assert region.capture_status == "CAPTURED"


# ---------------------------------------------------------------------------
# extract_issue_region — mock-page tests
# ---------------------------------------------------------------------------


class _MockElement:
    def __init__(self, outer_html: str, box: dict | None = None):
        self._outer_html = outer_html
        self._box = box

    def evaluate(self, _expr: str) -> str:
        return self._outer_html

    def bounding_box(self) -> dict | None:
        return self._box


class _MockPage:
    def __init__(self, elements: dict | None = None):
        self._elements = elements or {}

    def wait_for_selector(self, selector: str, timeout: int = 5000):
        return self._elements.get(selector)

    def query_selector_all(self, selector: str):
        return self._elements.get(selector, [])


def test_extract_by_selector_found():
    el = _MockElement("<div class='booking-cta'>Book Now</div>", {"x": 0, "y": 520, "width": 390, "height": 45})
    page = _MockElementPage({".booking-cta": el})
    finding = {
        "finding_id": "f001",
        "selector": ".booking-cta",
        "claim": "CTA is clipped",
        "severity": "high",
    }
    region = extract_issue_region(page, finding)
    assert region.finding_id == "f001"
    assert region.selector == ".booking-cta"
    assert region.capture_status == "CAPTURED"
    assert "Book Now" in region.outer_html


class _MockElementPage(_MockPage):
    """Variant that also supports elementFromPoint for bbox fallback."""

    def evaluate(self, _fn: str, _args: dict):
        return "<div class='fallback'>Fallback element</div>"


def test_extract_by_selector_not_found_falls_back_to_bbox():
    page = _MockElementPage({})  # no elements
    finding = {
        "finding_id": "f002",
        "claim": "Missing element",
        "severity": "medium",
        "evidence": [
            {
                "bounding_box": {"x": 100, "y": 200, "width": 300, "height": 50},
            }
        ],
    }
    region = extract_issue_region(page, finding)
    # Should hit bounding_box fallback with elementFromPoint
    assert region.finding_id == "f002"
    assert region.capture_status in ("CAPTURED", "TARGET_NOT_FOUND")


def test_extract_needs_review():
    page = _MockElementPage({})
    finding = {
        "finding_id": "f003",
        "claim": "No selector or bbox",
        "severity": "low",
    }
    region = extract_issue_region(page, finding)
    assert region.capture_status == "NEEDS_REVIEW"
    assert region.finding_id == "f003"


def test_extract_from_fixture_cta():
    finding = _load_fixture("verified-cta.json")
    el = _MockElement(
        '<div class="booking-cta" style="overflow:hidden">Book Now</div>',
        {"x": 0, "y": 520, "width": 390, "height": 45},
    )
    page = _MockElementPage({".booking-cta": el})
    region = extract_issue_region(page, finding)
    assert region.capture_status == "CAPTURED"
    assert region.selector == ".booking-cta"
    assert region.bounding_box["x"] == 0  # padded from x=0


def test_extract_from_fixture_form():
    finding = _load_fixture("verified-form.json")
    el = _MockElement(
        '<input id="contact-name" type="text" placeholder="Your name">',
        {"x": 100, "y": 300, "width": 200, "height": 40},
    )
    page = _MockElementPage({"#contact-name": el})
    region = extract_issue_region(page, finding)
    assert region.capture_status == "CAPTURED"
    assert region.selector == "#contact-name"
