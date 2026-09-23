"""Tests for LocalBusiness structured data extraction and comparison."""

from auditor_toolkit.local_seo.local_schema import (
    compare_schema_to_visible,
    extract_local_business_from_html,
    validate_localbusiness_schema,
)
from auditor_toolkit.local_seo.phone import normalize_phone


def test_extract_local_business_from_html_jsonld():
    html = """<script type="application/ld+json">
    {"@context": "https://schema.org", "@type": "LocalBusiness",
     "name": "ABC Plumbing", "telephone": "+6433795555",
     "address": {"@type": "PostalAddress", "streetAddress": "17 High St",
                 "addressLocality": "Wellington", "postalCode": "6011"}}
    </script>"""
    entities = extract_local_business_from_html(html)
    assert len(entities) == 1
    assert "LocalBusiness" in entities[0]["entity_type"]
    assert entities[0]["name"] == "ABC Plumbing"


def test_extract_local_business_from_html_empty():
    assert extract_local_business_from_html("<html><body>No schema</body></html>") == []


def test_extract_organization_schema():
    html = """<script type="application/ld+json">
    {"@context": "https://schema.org", "@type": "Organization",
     "name": "ABC Plumbing Ltd", "url": "https://abc.co.nz"}
    </script>"""
    entities = extract_local_business_from_html(html)
    assert len(entities) == 1
    assert "Organization" in entities[0]["entity_type"]


def test_compare_schema_to_visible_match():
    result = compare_schema_to_visible(
        schema_name="ABC Plumbing",
        visible_name="ABC Plumbing",
    )
    assert result[0]["status"] == "MATCH"


def test_compare_schema_to_visible_equivalent():
    result = compare_schema_to_visible(
        schema_name="ABC Plumbing Ltd",
        visible_name="ABC Plumbing Limited",
    )
    assert result[0]["status"] in ("MATCH", "EQUIVALENT_FORMAT", "PROBABLE_MATCH")


def test_compare_schema_to_visible_contradiction():
    result = compare_schema_to_visible(
        schema_phone=normalize_phone("+6433795555"),
        visible_phone=normalize_phone("+6433801234"),
    )
    phone = next(item for item in result if item["field"] == "phone")
    assert phone["status"] == "CONTRADICTION"


def test_validate_localbusiness_schema():
    html = """<script type="application/ld+json">
    {"@type": "LocalBusiness", "name": "ABC Plumbing",
     "telephone": "+6433795555",
     "address": {"@type": "PostalAddress", "streetAddress": "17 High St",
                 "addressLocality": "Wellington", "postalCode": "6011"}}
    </script>"""
    entity = extract_local_business_from_html(html)[0]
    issues = validate_localbusiness_schema(entity)
    assert not any(issue["field"] in {"name", "address", "telephone"} for issue in issues)


def test_validate_localbusiness_schema_geo():
    html = """<script type="application/ld+json">
    {"@type": "LocalBusiness", "name": "ABC Plumbing",
     "geo": {"@type": "GeoCoordinates", "latitude": -41.28, "longitude": 174.77}}
    </script>"""
    entity = extract_local_business_from_html(html)[0]
    issues = validate_localbusiness_schema(entity)
    assert not any(issue["field"] == "geo" for issue in issues)
