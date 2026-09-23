"""Tests for deterministic patch rules."""

from auditor_toolkit.proof.patches import (
    patch_broken_internal_url,
    patch_horizontal_overflow,
    patch_missing_form_label,
    patch_missing_image_dimensions,
    patch_poor_contrast,
)

# ---------------------------------------------------------------------------
# patch_missing_form_label
# ---------------------------------------------------------------------------

def test_patch_missing_form_label_injects_label():
    html = '<input id="contact-name" type="text" placeholder="Your name">'
    finding = {"finding_id": "f001", "selector": "#contact-name"}
    patched, manifest = patch_missing_form_label(html, finding)
    assert "<label" in patched
    assert 'for="contact-name"' in patched
    assert "Your name" in patched
    assert manifest.patch_type == "FORM_LABEL_PATCH"


def test_patch_missing_form_label_no_input():
    html = "<div>No inputs here</div>"
    finding = {"finding_id": "f002", "selector": "#missing"}
    patched, manifest = patch_missing_form_label(html, finding)
    # Should return original HTML unchanged when no input found
    assert "No inputs here" in patched


def test_patch_missing_form_label_uses_name_attr():
    html = '<input type="text" name="email-field">'
    finding = {"finding_id": "f003", "selector": ""}
    patched, manifest = patch_missing_form_label(html, finding)
    assert "<label" in patched
    assert "Email Field" in patched  # name attr converted to title case


# ---------------------------------------------------------------------------
# patch_horizontal_overflow
# ---------------------------------------------------------------------------

def test_patch_horizontal_overflow_inline_style():
    html = '<div style="overflow: hidden">Clipped content</div>'
    finding = {"finding_id": "f004", "selector": ".clipped"}
    patched, manifest = patch_horizontal_overflow(html, finding)
    assert "overflow: visible" in patched
    assert manifest.patch_type == "CSS_PATCH"


def test_patch_horizontal_overflow_no_match():
    html = "<div>No overflow style</div>"
    finding = {"finding_id": "f005", "selector": ".safe"}
    patched, _ = patch_horizontal_overflow(html, finding)
    # Falls back to wrapper
    assert patched.startswith("<div style=")


def test_patch_horizontal_overflow_css_rule():
    html = "<style>.booking-cta { overflow: hidden; }</style>"
    finding = {"finding_id": "f006", "selector": ".booking-cta"}
    patched, manifest = patch_horizontal_overflow(html, finding)
    assert "overflow: visible" in patched
    assert "overflow: hidden" not in patched


# ---------------------------------------------------------------------------
# patch_missing_image_dimensions
# ---------------------------------------------------------------------------

def test_patch_missing_image_dimensions_adds_attrs():
    html = '<img src="photo.jpg" alt="A photo">'
    finding = {"finding_id": "f007", "selector": "img"}
    patched, manifest = patch_missing_image_dimensions(html, finding)
    assert 'width="800"' in patched
    assert 'height="600"' in patched
    assert 'loading="lazy"' in patched


def test_patch_missing_image_dimensions_already_has_dims():
    html = '<img src="photo.jpg" width="400" height="300">'
    finding = {"finding_id": "f008", "selector": "img"}
    patched, manifest = patch_missing_image_dimensions(html, finding)
    assert patched == html  # unchanged


def test_patch_missing_image_dimensions_targeted():
    html = '<img id="hero" src="hero.jpg"><img src="thumb.jpg">'
    finding = {"finding_id": "f009", "selector": "#hero"}
    patched, manifest = patch_missing_image_dimensions(html, finding)
    # Only #hero should get dimensions added
    assert 'id="hero"' in patched
    assert 'width="800"' in patched


# ---------------------------------------------------------------------------
# patch_poor_contrast
# ---------------------------------------------------------------------------

def test_patch_poor_contrast_replaces_color():
    css = ".subtitle { color: #999; font-size: 14px; }"
    finding = {"finding_id": "f010", "selector": ".subtitle"}
    patched, manifest = patch_poor_contrast(css, finding)
    assert "color: #1a1a2e" in patched
    assert "color: #999" not in patched
    assert manifest.patch_type == "CSS_PATCH"


def test_patch_poor_contrast_no_low_contrast():
    css = ".good { color: #1a1a2e; }"
    finding = {"finding_id": "f011", "selector": ".good"}
    patched, manifest = patch_poor_contrast(css, finding)
    # Appends override when no low-contrast value found
    assert ".good { color: #1a1a2e; }" in patched


def test_patch_poor_contrast_name_color():
    css = ".text { color: grey; }"
    finding = {"finding_id": "f012", "selector": ".text"}
    patched, manifest = patch_poor_contrast(css, finding)
    assert "color: #1a1a2e" in patched


# ---------------------------------------------------------------------------
# patch_broken_internal_url
# ---------------------------------------------------------------------------

def test_patch_broken_internal_url_fixes_href():
    html = '<a href="/old-page">Link</a>'
    finding = {
        "finding_id": "f013",
        "selector": "a",
        "broken_url": "/old-page",
        "fixed_url": "/new-page",
    }
    patched, manifest = patch_broken_internal_url(html, finding)
    assert 'href="/new-page"' in patched
    assert 'href="/old-page"' not in patched
    assert manifest.patch_type == "HTML_ATTRIBUTE_PATCH"


def test_patch_broken_internal_url_not_found():
    html = '<a href="/correct-page">Link</a>'
    finding = {
        "finding_id": "f014",
        "selector": "a",
        "broken_url": "/missing-page",
        "fixed_url": "/new-page",
    }
    patched, manifest = patch_broken_internal_url(html, finding)
    assert patched == html  # unchanged


def test_patch_broken_internal_url_no_urls():
    html = "<a>No href</a>"
    finding = {
        "finding_id": "f015",
        "selector": "a",
        "broken_url": "/old",
        "fixed_url": "/new",
    }
    patched, manifest = patch_broken_internal_url(html, finding)
    assert patched == html
