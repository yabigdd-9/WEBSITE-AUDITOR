"""Integration test for full local SEO evidence pipeline."""

from auditor_toolkit.local_seo.pipeline import LocalSEOPipeline
from auditor_toolkit.local_seo.identity import build_identity


def test_full_pipeline_basic_site():
    """Run the full local SEO pipeline on a simple business site."""
    html = """
    <html>
    <head>
        <title>ABC Plumbing - Wellington</title>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "LocalBusiness",
            "name": "ABC Plumbing",
            "telephone": "+6431234567",
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
        <p>Call us: 03 123 4567</p>
        <p>Visit us at 17 High St, Wellington 6011</p>
        <p>Email: info@abcplumbing.co.nz</p>
    </body>
    </html>
    """
    pipeline = LocalSEOPipeline()
    result = pipeline.run(
        business_id="biz_abc",
        urls=["https://abcplumbing.co.nz/"],
        html_bodies={"https://abcplumbing.co.nz/": html},
    )

    assert result.business_id == "biz_abc"
    assert result.identity is not None
    assert result.identity.canonical_name


def test_full_pipeline_multi_location():
    """Run pipeline on a site with multiple location pages."""
    home = "<html><head><title>ABC Plumbing</title></head><body>Home</body></html>"
    chch = """<html><head><title>ABC Plumbing - Christchurch</title></head>
    <body>
        <h1>Christchurch Branch</h1>
        <p>123 Colombo St, Christchurch</p>
        <p>03 555 1000</p>
    </body></html>"""
    wellington = """<html><head><title>ABC Plumbing - Wellington</title></head>
    <body>
        <h1>Wellington Branch</h1>
        <p>17 High St, Wellington</p>
        <p>04 555 2000</p>
    </body></html>"""

    pipeline = LocalSEOPipeline()
    result = pipeline.run(
        business_id="biz_abc",
        urls=[
            "https://abc.co.nz/",
            "https://abc.co.nz/christchurch/",
            "https://abc.co.nz/wellington/",
        ],
        html_bodies={
            "https://abc.co.nz/": home,
            "https://abc.co.nz/christchurch/": chch,
            "https://abc.co.nz/wellington/": wellington,
        },
    )

    assert result.business_id == "biz_abc"
    assert len(result.location_pages) >= 2
