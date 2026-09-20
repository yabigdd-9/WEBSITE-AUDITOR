from __future__ import annotations

import json
import socket
from pathlib import Path

import httpx
import pytest

from auditor_toolkit.ai import fallback_drafts
from auditor_toolkit.checks import Finding, analyse_html, score_findings
from auditor_toolkit.common import Fetcher
from auditor_toolkit.pipeline import AuditOptions, run_audit

PUBLIC_ADDR = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443))]


def test_scores_are_oriented_and_missing_checks_are_not_healthy():
    scores = score_findings([Finding("x", "Defect", "Evidence", "high")], complete=True)
    assert scores["severity_score"] > 0
    assert scores["health_score"] < 100
    assert score_findings([], complete=False)["health_score"] is None


def test_findings_are_deduplicated_in_pipeline(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: PUBLIC_ADDR)
    html = "<title>x</title><img src='/x.png'><input type='checkbox' name='newsletter' checked>"
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=html, request=request))
    report = run_audit("https://example.com/", AuditOptions(output_root=tmp_path), Fetcher(transport=transport))
    assert report["status"] == "complete"
    unique_defects = {(d["defect_key"], d["impact"]) for d in report["defects"]}
    assert report["defect_count"] == len(unique_defects)
    assert Path(report["artifacts"]["json"]).exists()
    assert Path(report["artifacts"]["html"]).exists()


def test_redirect_to_private_destination_is_rejected(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: PUBLIC_ADDR)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            302,
            headers={"location": "http://127.0.0.1/private"},
            request=request,
        )
    )
    with pytest.raises(ValueError):
        Fetcher(transport=transport).get("https://example.com")


def test_analyse_html_avoids_ordinary_checked_box_false_positive():
    findings, _ = analyse_html("<input type='checkbox' name='terms' checked>", "https://example.com")
    assert "consent_prechecked" not in {finding.defect_key for finding in findings}


def test_report_escapes_injected_html(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: PUBLIC_ADDR)
    html = "<title><script>alert(1)</script></title><img src=x>"
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=html, request=request))
    report = run_audit("https://example.com/", AuditOptions(output_root=tmp_path), Fetcher(transport=transport))
    assert "<script>alert(1)</script>" not in Path(report["artifacts"]["html"]).read_text()


def test_ai_fallback_contains_all_requested_draft_types():
    assert {"metadata", "platform_fix", "outreach", "content_expansion", "bilingual"} <= set(fallback_drafts())


def test_report_json_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: PUBLIC_ADDR)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text="<title>ok</title>", request=request))
    report = run_audit("https://example.com/", AuditOptions(output_root=tmp_path), Fetcher(transport=transport))
    stored = json.loads(Path(report["artifacts"]["json"]).read_text())
    assert stored["run_id"] == report["run_id"]
    required = {"score", "severity_score", "health_score", "checks", "defects", "artifacts"}
    assert required <= set(stored)
