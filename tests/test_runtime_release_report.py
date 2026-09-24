"""Tests for release report and header-analysis outputs."""

import json

from auditor_toolkit.runtime.report import generate_release_report, save_report
from auditor_toolkit.server_technology import analyse_html


def test_release_report_readiness_and_persistence(tmp_path):
    not_ready = generate_release_report(
        commit_sha="abc123",
        soak_hours=167.9,
        gates={"tests": True, "security": False},
        metrics={"soak_start": "2026-09-01T00:00:00Z", "coverage": 0.9},
        limitations=["Browser checks skipped"],
    )
    assert not_ready.status == "NOT_READY"
    assert not_ready.gates_passed == 1
    json_path, markdown_path = save_report(not_ready, tmp_path)
    assert json.loads(json_path.read_text())["commit_sha"] == "abc123"
    assert "Browser checks skipped" in markdown_path.read_text()

    ready = generate_release_report(soak_hours=168, gates={"tests": True})
    limited = generate_release_report(
        soak_hours=200,
        gates={"tests": True},
        limitations=["Manual review pending"],
    )
    assert ready.status == "READY"
    assert limited.status == "READY_WITH_LIMITATIONS"
    assert generate_release_report().status == "NOT_READY"


def test_server_technology_reports_disclosing_headers():
    findings, evidence = analyse_html(
        "<html></html>",
        "https://example.test",
        {
            "Server": "Apache",
            "X-Powered-By": "PHP/8",
            "Via": "gateway",
            "X-Generator": "CMS",
            "CF-Ray": "ray-id",
            "X-Cache": "Akamai",
        },
    )
    keys = {finding.defect_key for finding in findings}
    assert keys == {
        "server-header",
        "x-powered-by-header",
        "via-header",
        "x-generator-header",
        "cloudflare-header",
        "akamai-header",
    }
    assert evidence == {}


def test_server_technology_is_empty_without_disclosing_headers():
    assert analyse_html("", "https://example.test", {}) == ([], {})
