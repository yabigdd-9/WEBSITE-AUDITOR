"""Tests for sandboxed prototype generation."""

from auditor_toolkit.proof.prototype import (
    PrototypeManifest,
    _content_id,
    create_prototype,
    patch_accessibility_role,
    patch_cta_visibility,
    patch_horizontal_overflow,
    patch_layout_shift,
    patch_missing_form_label,
    patch_missing_image_dimensions,
    patch_poor_contrast,
    patch_text_label,
)

# ---------------------------------------------------------------------------
# Content-addressed ID
# ---------------------------------------------------------------------------


def test_content_id_stable():
    assert _content_id("a", "b") == _content_id("a", "b")


def test_content_id_different():
    assert _content_id("a", "b") != _content_id("a", "c")


def test_content_id_is_hex():
    cid = _content_id("test")
    assert all(c in "0123456789abcdef" for c in cid)
    assert len(cid) == 12


# ---------------------------------------------------------------------------
# PrototypeManifest
# ---------------------------------------------------------------------------

def test_prototype_manifest_defaults():
    m = PrototypeManifest()
    assert m.patch_id == ""
    assert m.generated_by == "deterministic"


def test_prototype_manifest_to_dict():
    m = PrototypeManifest(patch_id="p1", finding_id="f1", patch_type="CSS_PATCH")
    d = m.to_dict()
    assert d["patch_id"] == "p1"
    assert d["finding_id"] == "f1"


# ---------------------------------------------------------------------------
# Deterministic patch functions
# ---------------------------------------------------------------------------

def test_patch_missing_form_label():
    finding = {
        "finding_id": "f001",
        "selector": "#contact-name",
        "placeholder": "Your name",
    }
    manifest = patch_missing_form_label(finding)
    assert manifest.patch_type == "FORM_LABEL_PATCH"
    assert manifest.finding_id == "f001"
    assert "label" in manifest.after_value.lower()
    assert manifest.generated_by == "deterministic"


def test_patch_horizontal_overflow():
    finding = {
        "finding_id": "f002",
        "selector": ".booking-cta",
    }
    manifest = patch_horizontal_overflow(finding)
    assert manifest.patch_type == "CSS_PATCH"
    assert "overflow: visible" in manifest.after_value


def test_patch_missing_image_dimensions():
    finding = {
        "finding_id": "f003",
        "selector": "#hero-img",
    }
    manifest = patch_missing_image_dimensions(finding)
    assert manifest.patch_type == "HTML_ATTRIBUTE_PATCH"
    assert "width=" in manifest.after_value


def test_patch_poor_contrast():
    finding = {
        "finding_id": "f004",
        "selector": ".subtitle",
    }
    manifest = patch_poor_contrast(finding)
    assert manifest.patch_type == "CSS_PATCH"
    assert "#1a1a2e" in manifest.after_value


def test_patch_broken_internal_url():
    finding = {
        "finding_id": "f005",
        "selector": "a.nav-link",
        "broken_url": "/old-page",
        "fixed_url": "/new-page",
    }
    from auditor_toolkit.proof.prototype import patch_broken_internal_url
    manifest = patch_broken_internal_url(finding)
    assert manifest.patch_type == "HTML_ATTRIBUTE_PATCH"
    assert "/old-page" in manifest.before_value
    assert "/new-page" in manifest.after_value


def test_patch_cta_visibility():
    finding = {
        "finding_id": "f006",
        "selector": ".mobile-cta",
    }
    manifest = patch_cta_visibility(finding)
    assert manifest.patch_type == "CTA_PATCH"
    assert "display: block" in manifest.after_value


def test_patch_accessibility_role():
    finding = {
        "finding_id": "f007",
        "selector": ".menu-toggle",
        "aria_role": "button",
        "accessible_name": "Toggle menu",
    }
    manifest = patch_accessibility_role(finding)
    assert manifest.patch_type == "ACCESSIBILITY_PATCH"
    assert 'role="button"' in manifest.after_value


def test_patch_layout_shift():
    finding = {
        "finding_id": "f008",
        "selector": ".hero-banner",
    }
    manifest = patch_layout_shift(finding)
    assert manifest.patch_type == "LAYOUT_PATCH"
    assert "min-height: 200px" in manifest.after_value


def test_patch_text_label():
    finding = {
        "finding_id": "f009",
        "selector": ".label",
        "before_text": "Click",
        "after_text": "Submit form",
    }
    manifest = patch_text_label(finding)
    assert manifest.patch_type == "TEXT_LABEL_PATCH"
    assert manifest.before_value == "Click"
    assert manifest.after_value == "Submit form"


# ---------------------------------------------------------------------------
# create_prototype
# ---------------------------------------------------------------------------

def test_create_prototype_with_patch_type():
    finding = {
        "finding_id": "f010",
        "selector": ".cta",
    }
    proto = create_prototype(finding, patch_type="CTA_PATCH")
    assert proto.manifest.patch_type == "CTA_PATCH"
    assert proto.html_body != ""
    assert proto.css_body != ""


def test_create_prototype_default_fallback():
    finding = {
        "finding_id": "f011",
        "selector": ".text",
    }
    proto = create_prototype(finding)  # no patch_type, no ai_generator
    assert proto.manifest is not None
    assert proto.html_body != ""


def test_create_prototype_html_contains_before_after():
    finding = {
        "finding_id": "f012",
        "selector": ".test",
    }
    proto = create_prototype(finding, patch_type="CSS_PATCH")
    assert "Before" in proto.html_body
    assert "After" in proto.html_body


def test_prototype_frozen():
    m = PrototypeManifest(patch_id="p1")
    try:
        m.patch_id = "p2"  # type: ignore[misc]
        assert False, "Should not be able to modify frozen dataclass"
    except (TypeError, AttributeError):
        pass
