"""Integration test for technology enrichment."""

from auditor_toolkit.technology.pipeline import enrich_technology
from auditor_toolkit.technology.report import generate_report


def _load(name: str) -> str:
    return open(f"tests/fixtures/technology/fingerprints/{name}.html").read()


def test_full_wordpress_pipeline():
    html = _load("wordpress")
    result = enrich_technology(html, url="https://wp-test.example.com")

    # Fingerprint detection
    assert result.fingerprint.cms is not None
    assert result.fingerprint.cms.name == "WordPress"

    # Version detection
    wp_versions = [v for v in result.versions if v.name == "WordPress"]
    assert len(wp_versions) >= 1
    assert wp_versions[0].detected_version == "5.8"
    assert wp_versions[0].is_outdated

    # Vulnerability check
    assert len(result.vulnerabilities) > 0

    # Report generation
    report = generate_report(result)
    assert "WordPress" in report
    assert "5.8" in report


def test_full_shopify_pipeline():
    html = _load("shopify")
    result = enrich_technology(html, url="https://shop-test.example.com")

    assert result.fingerprint.cms is not None
    assert result.fingerprint.cms.name == "Shopify"


def test_full_static_pipeline():
    html = _load("static")
    result = enrich_technology(html, url="https://static-test.example.com")

    assert result.fingerprint.cms is None
    assert result.versions == []
    assert result.vulnerabilities == []
