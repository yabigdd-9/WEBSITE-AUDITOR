"""Tests for location page detection and classification."""

from auditor_toolkit.local_seo.location_pages import (
    detect_location_pages,
    classify_location_page,
    LocationPageFeatures,
)


def test_detect_location_pages_path_pattern():
    urls = [
        "https://example.com/",
        "https://example.com/christchurch/",
        "https://example.com/auckland/",
        "https://example.com/locations/riccarton/",
        "https://example.com/about/",
    ]
    location_pages = detect_location_pages(urls)
    loc_urls = {p.url for p in location_pages}
    assert "https://example.com/christchurch/" in loc_urls
    assert "https://example.com/locations/riccarton/" in loc_urls
    assert "https://example.com/about/" not in loc_urls


def test_classify_location_page_branch():
    features = LocationPageFeatures(
        url="https://example.com/christchurch/",
        has_address=True,
        has_phone=True,
        has_localbusiness_schema=True,
        has_h1_with_city=True,
        has_breadcrumb=True,
    )
    classification = classify_location_page(features)
    assert classification.role in ("branch", "service_location", "location")


def test_classify_location_page_service_area():
    features = LocationPageFeatures(
        url="https://example.com/service-area/",
        has_address=False,
        has_phone=True,
        has_localbusiness_schema=False,
        has_h1_with_city=True,
        has_breadcrumb=False,
    )
    classification = classify_location_page(features)
    assert classification.role in ("service_area", "location")


def test_assess_location_page_quality_good():
    features = LocationPageFeatures(
        url="https://example.com/christchurch/",
        has_address=True,
        has_phone=True,
        has_localbusiness_schema=True,
        has_h1_with_city=True,
        has_breadcrumb=True,
        is_indexable=True,
        has_canonical=True,
        has_unique_content=True,
        has_map_link=True,
        word_count=500,
    )
    quality = assess_location_page_quality(features)
    assert quality.score > 0.7


def test_assess_location_page_quality_poor():
    features = LocationPageFeatures(
        url="https://example.com/christchurch/",
        has_address=False,
        has_phone=False,
        has_localbusiness_schema=False,
        has_h1_with_city=False,
        has_breadcrumb=False,
        is_indexable=False,
        has_canonical=False,
        has_unique_content=False,
        has_map_link=False,
        word_count=50,
    )
    quality = assess_location_page_quality(features)
    assert quality.score < 0.3


def test_detect_location_pages_no_locations():
    urls = [
        "https://example.com/",
        "https://example.com/about/",
        "https://example.com/contact/",
    ]
    assert detect_location_pages(urls) == []
