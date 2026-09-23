"""Integration tests for the full proof evidence pipeline.

Tests the end-to-end flow:
  finding → region extraction → prototype → before capture → after capture
"""

import json
import os
import tempfile

from auditor_toolkit.proof.environment import ProofEnvironment
from auditor_toolkit.proof.patches import (
    patch_horizontal_overflow,
    patch_missing_form_label,
)
from auditor_toolkit.proof.prototype import (
    Prototype,
    create_prototype,
)
from auditor_toolkit.proof.regions import IssueRegion, extract_issue_region

# Fixtures path
_FIXTURES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "fixtures", "proof", "findings"
)


def _load_fixture(name: str) -> dict:
    path = os.path.join(_FIXTURES_DIR, name)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


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


def test_cta_finding_full_pipeline():
    """Full pipeline for the CTA finding: extract region → create prototype."""
    finding = _load_fixture("verified-cta.json")

    # 1. Extract issue region
    el = _MockElement(
        '<div class="booking-cta" style="overflow:hidden">Book Now</div>',
        {"x": 0, "y": 520, "width": 390, "height": 45},
    )
    page = _MockPage({".booking-cta": el})
    region = extract_issue_region(page, finding)
    assert region.capture_status == "CAPTURED"
    assert region.selector == ".booking-cta"

    # 2. Create prototype for the overflow issue
    proto = create_prototype(finding, patch_type="CSS_PATCH")
    assert proto.manifest.patch_type == "CSS_PATCH"
    assert proto.manifest.finding_id == finding["finding_id"]

    # 3. Verify HTML body contains before/after
    assert "Before" in proto.html_body
    assert "After" in proto.html_body


def test_form_finding_full_pipeline():
    """Full pipeline for the form label finding."""
    finding = _load_fixture("verified-form.json")

    # 1. Extract issue region
    el = _MockElement(
        '<input id="contact-name" type="text" placeholder="Your name">',
        {"x": 100, "y": 300, "width": 200, "height": 40},
    )
    page = _MockPage({"#contact-name": el})
    region = extract_issue_region(page, finding)
    assert region.capture_status == "CAPTURED"
    assert region.selector == "#contact-name"

    # 2. Create prototype
    proto = create_prototype(finding, patch_type="FORM_LABEL_PATCH")
    assert proto.manifest.patch_type == "FORM_LABEL_PATCH"


def test_environment_matches_across_captures():
    """Before and after captures must use identical environments."""
    env1 = ProofEnvironment(
        browser_version="120.0",
        viewport_width=1280,
        viewport_height=900,
    )
    env2 = ProofEnvironment(
        browser_version="120.0",
        viewport_width=1280,
        viewport_height=900,
    )
    assert env1.matches(env2)


def test_environment_mismatch_detected():
    """Different environments should NOT match."""
    env_before = ProofEnvironment(viewport_width=1280)
    env_after = ProofEnvironment(viewport_width=1920)
    assert not env_before.matches(env_after)


def test_patch_roundtrip_html():
    """Apply a patch to HTML and verify the transformation."""
    html = '<div style="overflow: hidden">Clipped</div>'
    finding = {"finding_id": "f001", "selector": ".clipped"}

    patched, manifest = patch_horizontal_overflow(html, finding)
    assert "overflow: visible" in patched
    assert manifest.before_value == "overflow: hidden"
    assert manifest.after_value == "overflow: visible"


def test_patch_roundtrip_form_label():
    """Apply a form label patch and verify label injection."""
    html = '<input id="name" type="text" placeholder="Name">'
    finding = {"finding_id": "f002", "selector": "#name"}

    patched, manifest = patch_missing_form_label(html, finding)
    assert "<label" in patched
    assert 'for="name"' in patched
    assert manifest.patch_type == "FORM_LABEL_PATCH"


def test_prototype_from_patch():
    """Create a prototype directly from a patch manifest."""
    html = '<div style="overflow: hidden">Clipped</div>'
    finding = {"finding_id": "f003", "selector": ".clipped"}

    patched, manifest = patch_horizontal_overflow(html, finding)

    proto = Prototype(manifest=manifest, html_body=patched)
    assert proto.manifest.patch_id.startswith("patch_")
    assert "overflow: visible" in proto.html_body


def test_expected_capture_fixture():
    """Verify the expected capture fixture structure."""
    fixture_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "fixtures",
        "proof",
        "expected",
        "capture.json",
    )
    if os.path.exists(fixture_path):
        with open(fixture_path, encoding="utf-8") as f:
            data = json.load(f)
        # Should have the expected structure
        assert "viewport" in data or "capture_env" in data or "environment" in data


def test_expected_verification_fixture():
    """Verify the expected verification fixture structure."""
    fixture_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "fixtures",
        "proof",
        "expected",
        "verification.json",
    )
    if os.path.exists(fixture_path):
        with open(fixture_path, encoding="utf-8") as f:
            data = json.load(f)
        # Should have the expected structure
        assert "verdict" in data or "verification" in data
