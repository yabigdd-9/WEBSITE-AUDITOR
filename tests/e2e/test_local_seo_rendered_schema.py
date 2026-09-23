"""E2E test for local SEO rendered schema detection."""

from auditor_toolkit.local_seo.local_schema import (
    extract_local_business_from_html,
)


def test_rendered_schema_extraction():
    """Extract LocalBusiness schema from rendered HTML."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>ABC Plumbing</title>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "LocalBusiness",
            "name": "ABC Plumbing",
            "telephone": "+6431234567",
            "address": {
                "@type": "PostalAddress",
                "streetAddress": "17 High St",
                "addressLocality": "Wellington",
                "postalCode": "6011"
            },
            "geo": {
                "@type": "GeoCoordinates",
                "latitude": -41.2865,
                "longitude": 174.7762
            },
            "openingHours": "Mo-Fr 09:00-17:00"
        }
        </script>
    </head>
    <body>
        <h1>ABC Plumbing</h1>
    </body>
    </html>
    """
    entities = extract_local_business_from_html(html)
    assert len(entities) >= 1
    types = [e.get("@type") for e in entities]
    assert "LocalBusiness" in types


def test_rendered_schema_multiple_entities():
    """Multiple schema entities on same page."""
    html = """
    <script type="application/ld+json">
    [{"@type": "LocalBusiness", "name": "Branch A"},
     {"@type": "Organization", "name": "Head Office"}]
    </script>
    """
    entities = extract_local_business_from_html(html)
    assert len(entities) >= 2


def test_rendered_schema_no_schema():
    html = "<html><body>No structured data</body></html>"
    entities = extract_local_business_from_html(html)
    assert entities == []


def test_rendered_schema_geo_extraction():
    html = """
    <script type="application/ld+json">
    {"@type": "LocalBusiness",
     "geo": {"@type": "GeoCoordinates", "latitude": -41.28, "longitude": 174.77}}
    </script>
    """
    entities = extract_local_business_from_html(html)
    assert len(entities) >= 1
