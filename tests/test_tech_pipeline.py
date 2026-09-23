"""Tests for technology enrichment pipeline."""

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
