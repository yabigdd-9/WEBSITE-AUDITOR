"""E2E-style tests for LocalBusiness schema detection from rendered HTML."""

from auditor_toolkit.local_seo.local_schema import extract_local_business_from_html


def test_rendered_schema_extraction():
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
            "telephone": "+6433795555",
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
    <body><h1>ABC Plumbing</h1></body>
    </html>
    """
    entities = extract_local_business_from_html(html)
    assert len(entities) == 1
    assert "LocalBusiness" in entities[0]["entity_type"]
    assert entities[0]["geo"] is not None


def test_rendered_schema_multiple_entities():
    html = """
    <script type="application/ld+json">
    [{"@type": "LocalBusiness", "name": "Branch A"},
     {"@type": "Organization", "name": "Head Office"}]
    </script>
    """
    entities = extract_local_business_from_html(html)
    assert {entity["name"] for entity in entities} == {"Branch A", "Head Office"}


def test_rendered_schema_no_schema():
    assert extract_local_business_from_html("<html><body>No structured data</body></html>") == []


def test_rendered_schema_geo_extraction():
    html = """
    <script type="application/ld+json">
    {"@type": "LocalBusiness",
     "geo": {"@type": "GeoCoordinates", "latitude": -41.28, "longitude": 174.77}}
    </script>
    """
    entity = extract_local_business_from_html(html)[0]
    assert entity["geo"].latitude == -41.28
    assert entity["geo"].longitude == 174.77
