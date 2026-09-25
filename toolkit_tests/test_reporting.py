"""Regression tests for reporting engine.

Verify HTML report generation and SVG trend rendering.
"""
from pathlib import Path
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
