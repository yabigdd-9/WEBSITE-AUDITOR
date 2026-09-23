"""Tests for LocalBusiness structured data extraction and comparison."""

from auditor_toolkit.local_seo.local_schema import (
    extract_local_business_from_html,
    compare_schema_to_visible,
    validate_localbusiness_schema,
)
from auditor_toolkit.local_seo.schema import ConsistencyStatus


def test_extract_local_business_from_html_jsonld():
    html = '''<script type="application/ld+json">
    {"@context": "https://schema.org", "@type": "LocalBusiness",
     "name": "ABC Plumbing", "telephone": "+6431234567",
     "address": {"@type": "PostalAddress", "streetAddress": "17 High St",
                 "addressLocality": "Wellington", "postalCode": "6011"}}
    </script>'''
    entities = extract_local_business_from_html(html)
    assert len(entities) >= 1
    assert entities[0].get("@type") == "LocalBusiness"


def test_extract_local_business_from_html_empty():
    entities = extract_local_business_from_html("<html><body>No schema</body></html>")
    assert entities == []


def test_extract_organization_schema():
    html = '''<script type="application/ld+json">
    {"@context": "https://schema.org", "@type": "Organization",
     "name": "ABC Plumbing Ltd", "url": "https://abc.co.nz"}
    </script>'''
    entities = extract_local_business_from_html(html)
    types = [e.get("@type") for e in entities]
    assert "Organization" in types


def test_compare_schema_to_visible_match():
    schema_val = {"name": "ABC Plumbing", "telephone": "+6431234567"}
    visible_val = {"name": "ABC Plumbing", "telephone": "+6431234567"}
    result = compare_schema_to_visible(schema_val, visible_val, "name")
    assert result["status"] == "MATCH"


def test_compare_schema_to_visible_equivalent():
    schema_val = {"name": "ABC Plumbing Ltd"}
    visible_val = {"name": "ABC Plumbing Limited"}
    result = compare_schema_to_visible(schema_val, visible_val, "name")
    assert result["status"] in ("MATCH", "EQUIVALENT_FORMAT", "PROBABLE_MATCH")


def test_compare_schema_to_visible_contradiction():
    schema_val = {"telephone": "+6431234567"}
    visible_val = {"telephone": "+6439999999"}
    result = compare_schema_to_visible(schema_val, visible_val, "telephone")
    assert result["status"] == "CONTRADICTION"


def test_validate_localbusiness_schema():
    entity = {
        "@type": "LocalBusiness",
        "name": "ABC Plumbing",
        "telephone": "+6431234567",
    }
    normalized = validate_localbusiness_schema(entity)
    assert normalized["name"] == "ABC Plumbing"


def test_validate_localbusiness_schema_geo():
    entity = {
        "@type": "LocalBusiness",
        "geo": {"@type": "GeoCoordinates", "latitude": -41.28, "longitude": 174.77},
    }
    normalized = validate_localbusiness_schema(entity)
    assert "geo" in normalized
