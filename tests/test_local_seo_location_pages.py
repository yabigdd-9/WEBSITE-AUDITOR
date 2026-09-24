"""Tests for location page detection and classification."""

from auditor_toolkit.local_seo.location_pages import (
    LocationPageFeatures,
    classify_location_page,
    scan_urls_for_location_patterns,
)


def test_detect_location_pages_path_pattern():
    urls = [
        "https://example.com/",
        "https://example.com/christchurch/",
        "https://example.com/auckland/",
        "https://example.com/locations/riccarton/",
        "https://example.com/about/",
    ]
    matches = set(scan_urls_for_location_patterns(urls))
    assert "https://example.com/christchurch/" in matches
    assert "https://example.com/locations/riccarton/" in matches
    assert "https://example.com/about/" not in matches


def test_classify_location_page_branch():
    features = LocationPageFeatures(
        url="https://example.com/christchurch/",
        h1="Christchurch Branch",
        has_address_on_page=True,
        has_phone_on_page=True,
        has_localbusiness_schema=True,
        has_breadcrumbs=True,
        breadcrumb_text="Home > Locations > Christchurch",
    )
    result = classify_location_page(features)
    assert result.classification == "location"
    assert result.confidence >= 0.75


def test_classify_location_page_service_area():
    features = LocationPageFeatures(
        url="https://example.com/service-area/wellington/",
        h1="Serving Wellington",
        has_phone_on_page=True,
    )
    result = classify_location_page(features)
    assert result.classification in ("service_area", "location")


def test_strong_location_signals_raise_confidence():
    features = LocationPageFeatures(
        url="https://example.com/christchurch/",
        title="Christchurch Location",
        h1="Christchurch Branch",
        has_address_on_page=True,
        has_phone_on_page=True,
        has_localbusiness_schema=True,
        has_breadcrumbs=True,
        breadcrumb_text="Home > Locations > Christchurch",
    )
    assert classify_location_page(features).confidence >= 0.9


def test_non_location_page_stays_other():
    features = LocationPageFeatures(
        url="https://example.com/services/general/",
        title="General Services",
        h1="Our Services",
    )
    result = classify_location_page(features)
    assert result.classification == "other"
    assert result.confidence < 0.3


def test_detect_location_pages_no_locations():
    urls = [
        "https://example.com/",
        "https://example.com/about/",
        "https://example.com/contact/",
    ]
    assert scan_urls_for_location_patterns(urls) == []
