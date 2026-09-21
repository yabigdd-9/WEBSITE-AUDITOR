"""P5 evidence-first tests: findings carry evidence; scores derive from findings.

Gates:
  * every material defect (medium+) has an evidence summary
  * every score deduction links back to a finding_id
  * score totals equal the sum of their deductions (no invented numbers)
  * weak evidence is flagged heuristic, never silently
"""
from __future__ import annotations

import socket

import httpx

from auditor_toolkit.checks import Finding, analyse_html
from auditor_toolkit.common import Fetcher
from auditor_toolkit.pipeline import AuditOptions, run_audit
from auditor_toolkit.scoring import score_from_findings, weight_for

PUBLIC_ADDR = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443))]

BARE_HTML = (
    "<html><head></head><body><p>Hi</p>"
    "<img src='/x.png'><input type='checkbox' name='newsletter' checked></body></html>"
)


def test_html_findings_carry_evidence_remediation_and_effort():
    findings, _ = analyse_html(BARE_HTML, "https://example.com")
    assert findings, "bare page must produce findings"
    material = [f for f in findings if f.severity in {"medium", "high", "critical"}]
    assert material
    for f in material:
        assert f.observed or f.evidence_source or f.selector, (
            f.defect_key,
            "material finding without observed evidence",
        )
        assert f.remediation_action, (f.defect_key, "material finding without remediation")
        assert f.effort_band in {"XS", "S", "M", "L", "XL"}, f.defect_key
    keys = {f.defect_key for f in findings}
    assert "missing_title" in keys
    assert "consent_prechecked" in keys


def test_thin_content_and_schema_are_flagged_heuristic():
    findings, _ = analyse_html(BARE_HTML, "https://example.com")
    by_key = {f.defect_key: f for f in findings}
    assert by_key["thin_content_200_words"].confidence == "heuristic"
    assert by_key["schema_missing"].confidence == "heuristic"


def test_score_is_derived_from_findings_not_invented():
    records = [
        {
            "finding_id": "a1",
            "defect_key": "missing_title",
            "severity": "high",
            "confidence": "observed",
            "evidence_summary": "no <title> element",
        },
        {
            "finding_id": "b2",
            "defect_key": "thin_content_200_words",
            "severity": "medium",
            "confidence": "heuristic",
            "evidence_summary": "12 words",
        },
    ]
    breakdown = score_from_findings(records, complete=True)
    expected = weight_for("high") + weight_for("medium")
    assert breakdown.severity_total == expected
    assert breakdown.health_score == 100 - expected
    assert breakdown.heuristic_count == 1
    assert {d.finding_id for d in breakdown.deductions} == {"a1", "b2"}
    assert all(d.evidence_summary for d in breakdown.deductions)


def test_evidence_free_record_is_flagged_heuristic_never_silent():
    breakdown = score_from_findings(
        [{"finding_id": "z9", "defect_key": "mystery", "severity": "low"}], complete=True
    )
    assert breakdown.deductions[0].confidence == "heuristic"
    assert breakdown.heuristic_count == 1


def test_pipeline_report_links_every_deduction_to_a_defect(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: PUBLIC_ADDR)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, text=BARE_HTML, request=request)
    )
    report = run_audit(
        "https://example.com/", AuditOptions(output_root=tmp_path), Fetcher(transport=transport)
    )
    assert report["status"] == "complete"
    defect_ids = {d["finding_id"] for d in report["defects"]}
    # every material defect has evidence
    for d in report["defects"]:
        if d["severity"] in {"medium", "high", "critical"}:
            assert d.get("evidence_summary"), d["defect_key"]
    # every deduction links to a real defect
    breakdown = report["breakdown"]
    assert breakdown["deductions"], "score must decompose into deductions"
    assert {d["finding_id"] for d in breakdown["deductions"]} <= defect_ids
    # totals reconcile: no invented score
    assert breakdown["severity_total"] == report["severity_score"]
    assert breakdown["health_score"] == report["health_score"]
    assert breakdown["heuristic_count"] == sum(
        1 for d in breakdown["deductions"] if d["confidence"] == "heuristic"
    )


def test_legacy_finding_construction_still_works():
    f = Finding("x", "Defect", "Evidence", "high")
    assert f.effort_band == "M"
    assert f.remediation_automation == "HUMAN_REVIEW"
