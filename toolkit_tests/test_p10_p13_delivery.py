import json
from pathlib import Path

import pytest

from auditor_toolkit.demo import build_demo
from auditor_toolkit.packet import build_packet
from auditor_toolkit.quote import calculate_quote
from auditor_toolkit.remediation import build_remediation, classify


def report():
    return {
        "schema_version": 2,
        "run_id": "run-fixture",
        "url": "https://example.co.nz/",
        "domain": "example.co.nz",
        "status": "complete",
        "health_score": 72,
        "defects": [
            {
                "finding_id": "f1",
                "defect_key": "viewport",
                "defect": "Missing viewport metadata",
                "source_url": "https://example.co.nz/",
                "observed": "no viewport meta tag",
                "evidence_summary": "no viewport meta tag",
                "remediation_action": "Add viewport metadata.",
                "remediation_automation": "AUTO_SAFE",
                "effort_band": "XS",
                "confidence": "observed",
            },
            {
                "finding_id": "f2",
                "defect_key": "header-hsts",
                "defect": "Missing HSTS",
                "source_url": "https://example.co.nz/",
                "observed": "strict-transport-security absent",
                "evidence_summary": "strict-transport-security absent",
                "remediation_action": "Review deployment and add HSTS safely.",
                "remediation_automation": "HUMAN_REVIEW",
                "effort_band": "S",
                "confidence": "observed",
            },
        ],
        "artifacts": {},
    }


def test_p10_remediation_generates_preview_not_production_change(tmp_path):
    r = report()
    result = build_remediation(r, tmp_path / "remediation")
    assert result["source_run_id"] == r["run_id"]
    assert result["production_changes"] == 0
    assert result["external_dispatch"] is False
    assert result["review_required"] is True
    assert result["items"][0]["classification"] == "AUTO_SAFE"
    assert result["items"][1]["classification"] == "HUMAN_REVIEW"
    artifact = Path(result["items"][0]["artifact"])
    assert artifact.is_file()
    assert "viewport" in artifact.read_text().lower()


def test_p10_unknown_explicit_class_fails_hard():
    with pytest.raises(ValueError, match="Unknown remediation class"):
        classify({"defect_key": "x", "remediation_automation": "AUTO_MAGIC"})


def test_p12_quote_is_deterministic_and_rate_explicit():
    r = report()
    first = calculate_quote(r, "150")
    second = calculate_quote(r, "150")
    assert first == second
    assert first["rules_version"] == "quote-v1"
    assert first["currency"] == "NZD"
    assert first["llm_determined_price"] is False
    assert first["price_band_nzd"]["low"] == "300.00"
    assert DecimalString(first["price_band_nzd"]["high"]) > DecimalString(first["price_band_nzd"]["low"])
    assert first["review_required"] is True


def DecimalString(value):
    from decimal import Decimal
    return Decimal(value)


def test_p12_quote_refuses_missing_or_invalid_rate():
    r = report()
    for bad in (0, -1, "bad", 10001):
        with pytest.raises(ValueError):
            calculate_quote(r, bad)


def test_p11_demo_and_p13_packet_never_claim_live_change_or_send(tmp_path):
    r = report()
    remediation = build_remediation(r, tmp_path / "remediation")
    quote = calculate_quote(r, "150")
    demo = build_demo(r, remediation, tmp_path / "demo")

    assert demo["status"] == "CONCEPT_ONLY"
    assert demo["live_site_changed"] is False
    assert demo["improvement_claim_valid"] is False
    assert demo["external_deploy"] is False
    html = Path(demo["demo_html"]).read_text()
    assert "LOCAL CONCEPT ONLY" in html
    assert "Nothing on the source website has been changed" in html

    packet = build_packet(r, remediation, demo, quote, tmp_path / "packet")
    assert packet["approval_status"] == "HUMAN_APPROVAL_REQUIRED"
    assert packet["send_enabled"] is False
    assert packet["external_send_allowed"] is False
    assert packet["outbound_sent"] == 0
    assert packet["paid_ai_cost_usd"] == 0
    assert packet["contact"] is None
    assert packet["email_confidence"] == "NO_VERIFIED_EMAIL"
    assert len(packet["evidence"]) == 4
    assert Path(packet["draft_message_path"]).is_file()
    assert "not measured or guaranteed" in Path(packet["draft_message_path"]).read_text()


def test_packet_rejects_fake_after_claim(tmp_path):
    r = report()
    remediation = build_remediation(r, tmp_path / "remediation")
    quote = calculate_quote(r, "150")
    demo = build_demo(r, remediation, tmp_path / "demo")
    demo["improvement_claim_valid"] = True
    with pytest.raises(ValueError, match="must not claim"):
        build_packet(r, remediation, demo, quote, tmp_path / "packet")
