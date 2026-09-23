"""Tests for local SEO report generation."""

from auditor_toolkit.local_seo.identity import build_identity
from auditor_toolkit.local_seo.report import (
    LocalSEOReport,
    generate_benchmark,
    generate_report,
    render_markdown_report,
    save_report,
)


def test_generate_report_basic():
    entity = build_identity(
        business_id="biz_001",
        names=[("ABC Plumbing", "homepage")],
    )
    report = generate_report(
        run_id="run_001",
        site_url="https://abc.co.nz/",
        entity=entity.to_dict(),
        findings=[],
        contradictions=[],
    )
    assert isinstance(report, LocalSEOReport)
    assert report.run_id == "run_001"
    assert report.entity["business_id"] == "biz_001"


def test_report_has_required_fields():
    report = generate_report(
        run_id="run_002",
        entity=build_identity(
            business_id="biz_001",
            names=[("Test", "homepage")],
        ).to_dict(),
        findings=[],
        contradictions=[],
    )
    payload = report.to_dict()
    assert payload["run_id"] == "run_002"
    assert payload["findings"] == []
    assert "confidence_metrics" in payload
    assert "metadata" in payload


def test_full_report_renders_all_sections_and_persists_artifacts(tmp_path):
    report = generate_report(
        run_id="run_full",
        site_url="https://example.test",
        findings=[
            {
                "impact": "HIGH",
                "title": "Missing address",
                "confidence": 0.9,
                "page_url": "https://example.test/contact",
                "detail": "Address is absent.",
            },
            {"impact": "INFO", "defect_key": "schema-note", "confidence": 0.6},
            {"impact": "OTHER", "title": "Unclassified", "confidence": 0.5},
        ],
        contradictions=[
            {
                "field": "phone",
                "status": "CONTRADICTION",
                "schema_value": "+6431111111",
                "visible_value": "+6432222222",
            }
        ],
        location_pages=[
            {
                "url": "https://example.test/locations",
                "classification": "REAL",
                "confidence": 0.8,
            }
        ],
        service_area_classification={
            "classification": "SERVICE_AREA",
            "confidence": 0.85,
            "reasons": ["No storefront listed"],
        },
        corroboration={
            "overall_confidence": 0.7,
            "matches": [{"provider": "osm"}],
            "conflicts": [],
        },
        geo_corroboration=[
            {
                "status": "MATCH",
                "distance_km": 0.1234,
                "detail": "Within expected radius",
            }
        ],
        scoring_summary={"avg_confidence": 0.8},
        metadata={"source": "unit-test"},
    )

    markdown = render_markdown_report(report)
    benchmark = generate_benchmark(report)
    saved_dir = save_report(report, tmp_path)

    assert "## Business Classification" in markdown
    assert "## Findings" in markdown and "## Contradictions" in markdown
    assert "## Geographic Corroboration" in markdown
    assert "## External Corroboration" in markdown
    assert benchmark["findings_by_impact"] == {"HIGH": 1, "INFO": 1, "OTHER": 1}
    assert benchmark["contradictions_by_field"] == {"phone": 1}
    assert (saved_dir / "report.json").is_file()
    assert (saved_dir / "report.md").is_file()
    assert (saved_dir / "benchmark.json").is_file()
