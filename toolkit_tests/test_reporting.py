"""Regression tests for reporting engine.

Verify HTML report generation and SVG trend rendering.
"""
from auditor_toolkit.reporting import render_html_report, render_trend_svg

def test_render_html_report_smoke():
    report = {
        "domain": "test.com",
        "status": "ok",
        "defect_count": 0,
        "health_score": 100,
        "severity_score": 0,
        "defects": [],
    }
    html = render_html_report(report)
    assert "<title>Website audit - test.com</title>" in html
    assert "<strong>Health</strong><br>100</div>" in html

def test_render_trend_svg_smoke():
    report = {"health_score": 80}
    svg = render_trend_svg(report)
    assert 'width="160"' in svg # health * 2
    assert "Health 80" in svg

def test_render_trend_svg_unavailable():
    report = {"health_score": None}
    svg = render_trend_svg(report)
    assert "Health unavailable" in svg


def test_report_shows_finding_evidence_and_retest():
    report = {
        "domain": "example.test",
        "status": "complete",
        "defect_count": 1,
        "health_score": 92,
        "severity_score": 8,
        "defects": [{
            "severity": "medium",
            "defect": "Broken enquiry link",
            "source_url": "https://example.test/services",
            "observed_at": "2026-11-21T06:00:00Z",
            "observed": "Link <Request a quote> returns HTTP 404",
            "confidence": "observed",
            "business_impact": "Visitors cannot reach the enquiry page",
            "remediation_action": "Update the link to the published enquiry page",
            "check": "links",
        }],
    }
    html = render_html_report(report)
    assert "https://example.test/services" in html
    assert "2026-11-21T06:00:00Z" in html
    assert "&lt;Request a quote&gt; returns HTTP 404" in html
    assert "Visitors cannot reach the enquiry page" in html
    assert "Update the link to the published enquiry page" in html
    assert "Rerun links after the change" in html
