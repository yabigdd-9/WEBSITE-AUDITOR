import io
import json
from contextlib import redirect_stdout
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
    assert decimal_string(first["price_band_nzd"]["high"]) > decimal_string(first["price_band_nzd"]["low"])
    assert first["review_required"] is True


def decimal_string(value):
    from decimal import Decimal
    return Decimal(value)


def test_p12_quote_refuses_missing_or_invalid_rate():
    r = report()
    for bad in (0, -1, "bad", 10001):
        with pytest.raises(ValueError):
            calculate_quote(r, bad)


def test_p11_demo_and_p13_packet_never_claim_live_change_or_send(tmp_path):
    r = report()
    r["opportunity_score"] = 99.9  # ignored without component evidence
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
    assert packet["audit_score"] == 72
    assert packet["opportunity_score"] == 0
    assert packet["opportunity"]["formula_version"] == "opportunity-v1"
    assert packet["opportunity"]["provenance"]["commercial_score_evidence_ids"] == []
    assert len(packet["evidence"]) == 4
    assert not Path(packet["draft_message_path"]).is_absolute()
    assert (tmp_path / "packet" / packet["draft_message_path"]).is_file()
    assert "not measured or guaranteed" in (
        tmp_path / "packet" / packet["draft_message_path"]
    ).read_text()


def test_p13_packet_recomputes_opportunity_from_bound_evidence(tmp_path):
    r = report()
    r["commercial_score"] = 80
    r["commercial_score_evidence_ids"] = [17, 18]
    r["opportunity_score"] = 99.9  # ignored legacy/untrusted precomputed value
    remediation = build_remediation(r, tmp_path / "remediation")
    quote = calculate_quote(r, "150")
    demo = build_demo(r, remediation, tmp_path / "demo")

    packet = build_packet(
        r,
        remediation,
        demo,
        quote,
        tmp_path / "packet",
        demo_artifact_dir=tmp_path / "demo",
        contact={
            "email": "owner@example.co.nz",
            "selected": {"confidence_label": "VERIFIED_HIGH"},
            "provenance": {
                "verifier_version": "email-v2.0.0",
                "sources": [{
                    "source_url": "https://example.co.nz/contact?session=private",
                    "captured_at": "2026-09-28T00:00:00Z",
                    "capture_sha256": "a" * 64,
                    "first_party_observed": True,
                    "observed_email": "owner@example.co.nz",
                    "capture_path": "/private/local/capture.html",
                }],
            },
        },
    )

    assert packet["schema_version"] == 2
    assert packet["audit_score"] == 72
    assert packet["opportunity_score"] == packet["opportunity"]["opportunity_score"]
    assert packet["opportunity_score"] < 99.9
    assert packet["opportunity"]["formula_version"] == "opportunity-v1"
    assert packet["opportunity"]["components"]["need"] == 0.25
    assert packet["opportunity"]["components"]["business_value"] == 0.8
    assert packet["opportunity"]["components"]["contactability"] == 0.95
    assert packet["opportunity"]["provenance"]["commercial_score_evidence_ids"] == [17, 18]
    assert packet["contact"] == "owner@example.co.nz"
    assert packet["contact_provenance"]["sources"] == [{
        "url": "https://example.co.nz/contact",
        "captured_at": "2026-09-28T00:00:00Z",
        "sha256": "a" * 64,
    }]
    assert "capture_path" not in json.dumps(packet)


def test_p13_packet_imports_run_bound_pipeline_qualification(tmp_path):
    r = report()
    remediation = build_remediation(r, tmp_path / "remediation")
    quote = calculate_quote(r, "150")
    demo = build_demo(r, remediation, tmp_path / "demo")
    qualification = {
        "audit_run_id": r["run_id"],
        "commercial_score": 80,
        "commercial_score_evidence_ids": [17, 18],
        "commercial_score_industry": "electrical",
        "commercial_score_basis": "fresh_verified_capture",
        "technical_score": 72,
        "technical_score_method": "toolkit-p5-v1",
        "technical_score_finding_ids": [d["finding_id"] for d in r["defects"]],
        "technical_score_evidence_complete": True,
    }
    contact = {
        "email": "owner@example.co.nz",
        "selected": {"confidence_label": "VERIFIED_HIGH"},
        "provenance": {
            "verifier_version": "email-v2.0.0",
            "sources": [{
                "source_url": "https://example.co.nz/contact?token=private",
                "captured_at": "2026-09-28T00:00:00Z",
                "capture_sha256": "b" * 64,
                "first_party_observed": True,
                "observed_email": "owner@example.co.nz",
            }],
        },
    }

    packet = build_packet(
        r, remediation, demo, quote, tmp_path / "packet",
        qualification_evidence=qualification,
        contact=contact,
        demo_artifact_dir=tmp_path / "demo",
    )

    assert packet["qualification"]["commercial_score_evidence_ids"] == [17, 18]
    assert packet["opportunity"]["components"]["business_value"] == 0.8
    assert packet["opportunity"]["provenance"]["commercial_score_evidence_ids"] == [17, 18]
    assert any(item["kind"] == "qualification" for item in packet["evidence"])


def test_p13_packet_rejects_qualification_from_another_audit_run(tmp_path):
    r = report()
    remediation = build_remediation(r, tmp_path / "remediation")
    quote = calculate_quote(r, "150")
    demo = build_demo(r, remediation, tmp_path / "demo")
    qualification = {
        "audit_run_id": "different-run",
        "commercial_score": 80,
        "commercial_score_evidence_ids": [17],
        "technical_score": 72,
        "technical_score_method": "toolkit-p5-v1",
        "technical_score_finding_ids": [d["finding_id"] for d in r["defects"]],
        "technical_score_evidence_complete": True,
    }
    with pytest.raises(ValueError, match="same audit run"):
        build_packet(
            r, remediation, demo, quote, tmp_path / "packet",
            qualification_evidence=qualification,
        )


def test_wa_packet_cli_imports_pipeline_scores_and_email_provenance(tmp_path, monkeypatch):
    from auditor_toolkit.cli import main

    r = report()
    remediation = build_remediation(r, tmp_path / "remediation")
    quote = calculate_quote(r, "150")
    demo = build_demo(r, remediation, tmp_path / "demo")
    inputs = {
        "report.json": r,
        "remediation.json": remediation,
        "demo.json": demo,
        "quote.json": quote,
        "qualification.json": {
            "audit_run_id": r["run_id"],
            "commercial_score": 80,
            "commercial_score_evidence_ids": [17],
            "technical_score": 72,
            "technical_score_method": "toolkit-p5-v1",
            "technical_score_finding_ids": [d["finding_id"] for d in r["defects"]],
            "technical_score_evidence_complete": True,
        },
        "contact.json": {
            "contact": {
                "email": "owner@example.co.nz",
                "selected": {"confidence_label": "VERIFIED_HIGH"},
                "provenance": {
                    "verifier_version": "email-v2.0.1",
                    "sources": [{
                        "source_url": "https://example.co.nz/contact?session=private",
                        "captured_at": "2026-09-28T00:00:00Z",
                        "capture_sha256": "c" * 64,
                        "first_party_observed": True,
                        "observed_email": "owner@example.co.nz",
                    }],
                },
            },
        },
    }
    for name, value in inputs.items():
        (tmp_path / name).write_text(json.dumps(value))
    monkeypatch.chdir(tmp_path)
    output = io.StringIO()
    with redirect_stdout(output):
        assert main([
            "packet", "report.json", "remediation.json", "demo.json", "quote.json",
            "--output-dir", "packet",
            "--qualification-evidence", "qualification.json",
            "--contact-evidence", "contact.json",
        ]) == 0

    packet = json.loads(output.getvalue())
    assert packet["contact"] == "owner@example.co.nz"
    assert packet["opportunity"]["components"]["business_value"] == 0.8
    assert packet["opportunity"]["provenance"]["commercial_score_evidence_ids"] == [17]
    assert packet["external_send_allowed"] is False
    assert packet["outbound_sent"] == 0
    assert "capture_path" not in output.getvalue()
    assert "session=private" not in output.getvalue()


def test_p13_drops_verified_email_without_matching_first_party_capture(tmp_path):
    r = report()
    remediation = build_remediation(r, tmp_path / "remediation")
    quote = calculate_quote(r, "150")
    demo = build_demo(r, remediation, tmp_path / "demo")

    packet = build_packet(
        r,
        remediation,
        demo,
        quote,
        tmp_path / "packet",
        contact={
            "email": "owner@example.co.nz",
            "selected": {"confidence_label": "VERIFIED_HIGH"},
        },
    )

    assert packet["contact"] is None
    assert packet["email_confidence"] == "NO_VERIFIED_EMAIL"
    assert packet["contact_provenance"] is None
    assert packet["opportunity"]["components"]["contactability"] == 0


def test_p13_copies_screenshots_into_packet_without_absolute_paths(tmp_path):
    r = report()
    remediation = build_remediation(r, tmp_path / "remediation")
    quote = calculate_quote(r, "150")
    demo = build_demo(r, remediation, tmp_path / "demo")
    screenshot = tmp_path / "demo" / "before-source.png"
    screenshot.write_bytes(b"\x89PNG\r\n\x1a\nsynthetic")
    from hashlib import sha256
    demo["before"] = {
        "path": str(screenshot),
        "sha256": sha256(screenshot.read_bytes()).hexdigest(),
        "kind": "captured_source",
    }

    packet = build_packet(
        r,
        remediation,
        demo,
        quote,
        tmp_path / "packet",
        demo_artifact_dir=tmp_path / "demo",
    )

    image_ref = packet["before_images"][0]
    assert image_ref["path"] == "screenshots/before.png"
    assert not Path(image_ref["path"]).is_absolute()
    assert (tmp_path / "packet" / image_ref["path"]).read_bytes() == screenshot.read_bytes()
    assert str(screenshot) not in json.dumps(packet)


def test_p9_caps_normalized_effort_for_large_quotes():
    from auditor_toolkit.opportunity import opportunity_from_packet_evidence

    r = report()
    r["commercial_score"] = 80
    r["commercial_score_evidence_ids"] = [17]
    for index, key in enumerate(("schema_missing", "no-contact-path", "viewport", "sitemap-missing"), 3):
        r["defects"].append({
            "finding_id": f"f{index}",
            "defect_key": key,
            "observed": "synthetic evidence",
            "evidence_summary": "synthetic evidence",
            "confidence": "observed",
            "effort_band": "XL",
        })
    remediation = {
        "source_run_id": r["run_id"],
        "items": [
            {"finding_id": finding["finding_id"], "classification": "HUMAN_REVIEW"}
            for finding in r["defects"]
        ],
    }
    quote = {
        "source_run_id": r["run_id"],
        "rules_version": "quote-v1",
        "estimated_hours": {"high": "276.00"},
    }

    result = opportunity_from_packet_evidence(r, remediation, quote, {
        "email": "owner@example.co.nz",
        "selected": {"confidence_label": "VERIFIED_HIGH"},
        "provenance": {
            "sources": [{
                "source_url": "https://example.co.nz/contact",
                "captured_at": "2026-09-28T00:00:00Z",
                "capture_sha256": "b" * 64,
                "first_party_observed": True,
                "observed_email": "owner@example.co.nz",
            }]
        },
    })

    assert result["components"]["effort"] == 1


def test_packet_rejects_fake_after_claim(tmp_path):
    r = report()
    remediation = build_remediation(r, tmp_path / "remediation")
    quote = calculate_quote(r, "150")
    demo = build_demo(r, remediation, tmp_path / "demo")
    demo["improvement_claim_valid"] = True
    with pytest.raises(ValueError, match="must not claim"):
        build_packet(r, remediation, demo, quote, tmp_path / "packet")
