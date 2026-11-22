"""Tests for technology fingerprinting."""

from auditor_toolkit.technology.fingerprints import (
    detect_analytics,
    detect_cdn,
    detect_cms,
    detect_ecommerce,
    detect_framework,
    detect_language,
    detect_payment,
    detect_server,
    fingerprint,
)

# Fixtures
_WP_HTML = open("tests/fixtures/technology/fingerprints/wordpress.html").read()
_SHOPIFY_HTML = open("tests/fixtures/technology/fingerprints/shopify.html").read()
_STATIC_HTML = open("tests/fixtures/technology/fingerprints/static.html").read()


def test_detect_cms_wordpress():
    result = detect_cms(_WP_HTML)
    assert result is not None
    assert result.name == "WordPress"
    assert result.confidence > 0.5


def test_detect_cms_shopify():
    result = detect_cms(_SHOPIFY_HTML)
    assert result is not None
    assert result.name == "Shopify"


def test_detect_cms_static():
    result = detect_cms(_STATIC_HTML)
    assert result is None


def test_detect_framework_jquery():
    result = detect_framework(_WP_HTML)
    assert result is not None
    assert result.name == "jQuery"


def test_detect_framework_static():
    result = detect_framework(_STATIC_HTML)
    assert result is None


def test_detect_analytics_none():
    results = detect_analytics(_STATIC_HTML)
    assert results == []


def test_detect_server_with_headers():
    headers = {"Server": "nginx/1.25"}
    result = detect_server(headers)
    assert result is not None
    assert result.name == "nginx"


def test_detect_server_none():
    result = detect_server({})
    assert result is None


def test_detect_ecommerce_none():
    result = detect_ecommerce(_STATIC_HTML)
    assert result is None


def test_detect_payment_none():
    results = detect_payment(_STATIC_HTML)
    assert results == []


def test_detect_cdn_from_headers():
    headers = {"CF-RAY": "abc123"}
    result = detect_cdn(headers)
    assert result is not None
    assert result.name == "Cloudflare"


def test_detect_language_php():
    headers = {"X-Powered-By": "PHP/8.1"}
    result = detect_language(headers)
    assert result is not None
    assert result.name == "PHP"


def test_fingerprint_full():
    fp = fingerprint(_WP_HTML)
    assert fp.cms is not None
    assert fp.cms.name == "WordPress"
    assert fp.framework is not None  # jQuery detected
    assert fp.analytics == []  # No analytics in fixture
    assert len(fp.all_detections) >= 2


def test_fingerprint_shopify():
    fp = fingerprint(_SHOPIFY_HTML)
    assert fp.cms is not None
    assert fp.cms.name == "Shopify"


def test_fingerprint_static():
    fp = fingerprint(_STATIC_HTML)
    assert fp.cms is None
    assert fp.framework is None
