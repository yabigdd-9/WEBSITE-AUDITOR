"""Tests for local SEO pipeline integration."""

from auditor_toolkit.local_seo.pipeline import (
    LocalSEOPipeline,
    PipelineResult,
)


def test_LocalSEOPipeline_empty():
    result = LocalSEOPipeline(
        business_id="biz_001",
        urls=[],
    )
    assert result.business_id == "biz_001"
    assert result.findings == []


def test_LocalSEOPipeline_basic():
    """Basic pipeline execution with minimal HTML."""
    html = "<html><head><title>ABC Plumbing</title></head>" \
           "<body><p>Call us: 03 123 4567</p>" \
           "<p>17 High St, Wellington</p></body></html>"
    result = LocalSEOPipeline(
        business_id="biz_001",
        urls=["https://abc.co.nz/"],
        html_bodies={"https://abc.co.nz/": html},
    )
    assert result.business_id == "biz_001"
    assert result.identity is not None
