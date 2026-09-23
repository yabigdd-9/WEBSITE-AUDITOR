"""Tests for the canonical local SEO pipeline API."""

from auditor_toolkit.local_seo.pipeline import LocalSEOPipeline, PipelineResult


def test_local_seo_pipeline_empty():
    pipeline = LocalSEOPipeline(run_id="biz_001")
    result = pipeline.run()
    assert isinstance(result, PipelineResult)
    assert result.run_id == "biz_001"
    assert result.entity is not None
    assert result.entity["business_id"] == "biz-biz_001"


def test_local_seo_pipeline_basic():
    html = (
        "<html><head><title>ABC Plumbing - Wellington</title></head>"
        "<body><p>Call us: 03 379 5555</p>"
        "<p>17 High Street, Wellington 6011</p></body></html>"
    )
    pipeline = LocalSEOPipeline(run_id="basic")
    result = pipeline.run(html=html, url="https://abc.co.nz/")

    assert result.entity is not None
    assert result.entity["canonical_name"] == "ABC Plumbing"
    assert result.errors == []
