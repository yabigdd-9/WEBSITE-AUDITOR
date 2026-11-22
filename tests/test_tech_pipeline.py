"""Tests for technology enrichment pipeline."""

import pytest

from auditor_toolkit.tech import analyse_html as analyse_technology_html
from auditor_toolkit.tech import detect_technology
from auditor_toolkit.technology.pipeline import enrich_technology


def _load(name: str) -> str:
    return open(f"tests/fixtures/technology/fingerprints/{name}.html").read()


def test_enrich_wordpress():
    html = _load("wordpress")
    result = enrich_technology(html, url="https://example.com")
    assert result.fingerprint.cms is not None
    assert result.fingerprint.cms.name == "WordPress"
    assert result.errors == []


def test_enrich_shopify():
    html = _load("shopify")
    result = enrich_technology(html)
    assert result.fingerprint.cms is not None
    assert result.fingerprint.cms.name == "Shopify"


def test_enrich_static():
    html = _load("static")
    result = enrich_technology(html)
    assert result.fingerprint.cms is None


def test_enrich_with_errors():
    result = enrich_technology("<html></html>", url="https://example.com", run_id="test-001")
    assert result.url == "https://example.com"
    assert result.run_id == "test-001"


def test_legacy_detector_handles_missing_and_empty_generator():
    assert detect_technology("<html></html>", {}) == []
    assert detect_technology(
        '<meta name="generator" content="">',
        {},
    ) == []


def test_legacy_detector_extracts_generator_version():
    result = detect_technology(
        '<meta name="generator" content="WordPress 6.4.2">',
        {},
    )
    wordpress = next(item for item in result if item.technology == "WordPress")
    assert wordpress.version == "6.4.2"
    assert wordpress.version_confidence == 0.9


def test_legacy_technology_analysis_keeps_detected_software_as_evidence():
    html = (
        '<meta name="generator" content="WordPress 6.4.2">'
        '<script src="https://cdn.shopify.com/shopify.js"></script>'
    )
    findings, evidence = analyse_technology_html(html, "https://example.com", {})
    assert findings == []  # A fingerprint alone is not a defect.
    technologies = {item["technology"]: item for item in evidence["technologies"]}
    assert technologies["WordPress"]["version"] == "6.4.2"
    assert technologies["WordPress"]["source_url"] == "https://example.com"
    assert technologies["Shopify"]["category"] == "Ecommerce"


def test_legacy_technology_analysis_empty_html_remains_valid():
    findings, evidence = analyse_technology_html("<html></html>", "https://example.com", {})
    assert findings == []
    assert evidence == {"technologies": []}


@pytest.mark.parametrize(
    ("html", "headers", "name", "category"),
    [
        ("", {"Set-Cookie": "woocommerce_cart_hash=abc"}, "WooCommerce", "Ecommerce"),
        ("", {"X-Shopify-Stage": "production"}, "Shopify", "Ecommerce"),
        ('<meta name="generator" content="Wix.com Website Builder">', {}, "Wix", "CMS"),
        ('<meta name="generator" content="Squarespace">', {}, "Squarespace", "CMS"),
        ('<div data-reactroot></div>', {}, "React", "JavaScript Framework"),
        ('<script src="react.js"></script>', {}, "React", "JavaScript Framework"),
        ('<link href="bootstrap.css" rel="stylesheet">', {}, "Bootstrap", "CSS Framework"),
        ('<script src="bootstrap.js"></script>', {}, "Bootstrap", "CSS Framework"),
        ('<script src="jquery.js"></script>', {}, "jQuery", "JavaScript Library"),
        ('<script src="google-analytics.js"></script>', {}, "Google Analytics", "Analytics"),
        ("<script>ga('send', 'pageview')</script>", {}, "Google Analytics", "Analytics"),
    ],
)
def test_passive_fingerprints_preserve_evidence_without_claiming_defects(
    html, headers, name, category
):
    findings, evidence = analyse_technology_html(html, "https://example.com/page", headers)
    assert findings == []
    assert len(evidence["technologies"]) == 1
    detected = evidence["technologies"][0]
    assert detected["technology"] == name
    assert detected["category"] == category
    assert detected["source_url"] == "https://example.com/page"
    assert detected["evidence"]
    assert 0 < detected["confidence"] <= 1
    assert detected["version"] is None


def test_unversioned_wordpress_does_not_invent_a_version():
    detected, = detect_technology('<meta name="generator" content="WordPress">', {})
    assert detected.technology == "WordPress"
    assert detected.version is None
    assert detected.confidence == 0.7
    assert detected.version_confidence == 0.7


@pytest.mark.parametrize("html", ['<meta name="generator">', '<meta name="generator" content="Other CMS">'])
def test_unrecognized_generator_does_not_create_a_fingerprint(html):
    assert detect_technology(html, {}) == []
