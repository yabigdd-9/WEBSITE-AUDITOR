from auditor_core.crawl import discover_internal_links, merge_site_findings


def test_discover_internal_links_is_same_origin_and_deduplicated():
    html = """
    <a href="/about">About</a>
    <a href="https://example.co.nz/about#team">About duplicate</a>
    <a href="contact?from=nav">Contact</a>
    <a href="https://other.example/page">External</a>
    <a href="mailto:test@example.co.nz">Email</a>
    """
    links = discover_internal_links(html, "https://example.co.nz/")
    assert links == [
        "https://example.co.nz/about",
        "https://example.co.nz/contact?from=nav",
    ]


def test_merge_site_findings_preserves_page_provenance():
    pages = [
        {
            "url": "https://example.co.nz/",
            "findings": [{"check_id": "seo.h1_missing", "message": "Missing H1"}],
        },
        {
            "url": "https://example.co.nz/contact",
            "findings": [{"check_id": "seo.title_missing", "message": "Missing title"}],
        },
    ]
    merged = merge_site_findings(pages)
    assert merged[0]["page_url"] == "https://example.co.nz/"
    assert merged[1]["page_url"] == "https://example.co.nz/contact"
