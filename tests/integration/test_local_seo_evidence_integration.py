"""Integration tests for the full local SEO evidence pipeline."""

from auditor_toolkit.local_seo.pipeline import LocalSEOPipeline


def test_full_pipeline_basic_site():
    html = """
    <html>
    <head>
        <title>ABC Plumbing - Wellington</title>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "LocalBusiness",
            "name": "ABC Plumbing",
            "telephone": "+6433795555",
            "address": {
                "@type": "PostalAddress",
                "streetAddress": "17 High Street",
                "addressLocality": "Wellington",
                "postalCode": "6011"
            }
        }
        </script>
    </head>
    <body>
        <h1>ABC Plumbing Wellington</h1>
        <p>Call us: 03 379 5555</p>
        <p>Visit us at 17 High Street, Wellington 6011</p>
        <p>Email: info@abcplumbing.co.nz</p>
    </body>
    </html>
    """
    result = LocalSEOPipeline(run_id="abc").run(
        html=html,
        url="https://abcplumbing.co.nz/",
    )

    assert result.entity is not None
    assert result.entity["canonical_name"] == "ABC Plumbing"
    assert result.entity["business_id"] == "biz-abc"
    assert result.errors == []


def test_full_pipeline_multi_location_url_detection():
    home = "<html><head><title>ABC Plumbing</title></head><body>Home</body></html>"
    result = LocalSEOPipeline(run_id="multi").run(
        html=home,
        url="https://abc.co.nz/",
        sitemap_urls=[
            "https://abc.co.nz/",
            "https://abc.co.nz/christchurch/",
            "https://abc.co.nz/wellington/",
        ],
    )

    urls = {page["url"] for page in result.location_pages}
    assert "https://abc.co.nz/christchurch/" in urls
    assert "https://abc.co.nz/wellington/" in urls
