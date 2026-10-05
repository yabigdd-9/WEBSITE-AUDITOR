"""Synthetic, offline tests for the local draft bridge; no runtime DB/provider."""
import copy
import hashlib
import json
import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "money-machine"))
import mm_contact_draft_bridge as bridge  # noqa: E402

from auditor_toolkit.demo import build_demo  # noqa: E402
from auditor_toolkit.packet import build_packet  # noqa: E402
from auditor_toolkit.remediation import build_remediation  # noqa: E402

STATIC_AUDIT = bridge._static_audit


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    def denied(*args, **kwargs):
        raise AssertionError("Network/provider access forbidden in draft tests")
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setenv("MM_ROOT", str(tmp_path))
    monkeypatch.setenv("MM_EXTERNAL_SEND_DISABLED", "1")
    monkeypatch.delenv("MM_HOURLY_RATE_NZD", raising=False)
    monkeypatch.delenv("MM_SIGN_OFF", raising=False)


@pytest.fixture
def proof(tmp_path, monkeypatch):
    stamp = datetime.now(timezone.utc).isoformat()
    raw = b'<html lang="en"><head><title>Acme contact</title></head><body><h1>Acme</h1><a href="mailto:info@acme.co.nz">info@acme.co.nz</a></body></html>'
    path = tmp_path / "capture.html"
    path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    business = {"id": "business-1", "live_business_id": 1, "name": "Acme",
                "region": "Auckland", "public_website": "https://acme.co.nz/",
                "unit_scope": "Acme Auckland", "pipeline_state_at_freeze": "NEEDS_REVIEW"}
    capture = {"url": business["public_website"], "capture_path": str(path),
               "capture_hash": digest, "captured_at": stamp}
    selected = {"email": "info@acme.co.nz", "verifier_version": bridge.email.VERSION,
                "confidence_label": "VERIFIED_HIGH", "business_match": True,
                "domain_match": True, "mx_present": True, "domain_accepts_mail": True,
                "dns_checked_at": stamp, "rejection_reasons": [], "role_account": "general",
                "evidence": [{"capture_path": str(path), "capture_hash": digest, "observed_at": stamp}]}
    row = {"company": "Acme", "website": business["public_website"],
           "judge": {"route": "MACHINE_SUPPORTED_RECOMMENDATION"},
           "verifier": {"identity": {"status": "HIGH", "canonical_root_domain": "acme.co.nz", "page_evidence": [capture]}, "selected": selected},
           "proofer": {"passed": True, "checks": {key: True for key in bridge.PROOF_CHECKS},
                       "sources": [{"source_url": business["public_website"], "capture_sha256": digest}]}}
    receipt = {"status": "COMPLETE", "reviewed_at": stamp, "live_business_id": 1, "row": row}
    report = {"run_id": "test-static", "url": business["public_website"], "domain": "acme.co.nz",
              "status": "STATIC_CAPTURE_CONTENT_ONLY", "defects": [{"finding_id": "f1", "defect_key": "image-alt", "defect": "Image has no text alternative", "observed": "img#hero lacks an alt attribute", "severity": "medium", "confidence": "observed", "effort_band": "S", "source_url": business["public_website"]}]}
    monkeypatch.setattr(bridge, "_static_audit", lambda *args: (copy.deepcopy(report), "SYNTHETIC_AUDIT"))
    return business, receipt, tmp_path, path


def test_supported_proof_prepares_price_free_draft_and_reuses(proof):
    business, receipt, root, _ = proof
    result = bridge.prepare_draft(business, receipt, root)
    assert result["status"] == "DRAFT_READY"
    assert result["external_sends"] == result["model_calls"] == result["production_email_writes"] == 0
    packet = json.loads(Path(result["packet_path"]).read_text())
    assert packet["price"] is None
    assert "NZ$" not in packet["body"]
    assert "scope and cost" in packet["body"]
    assert packet["human_precision_label"] is None
    assert packet["authority"] == "DRAFT_ONLY"
    assert result["technical_holds"] == ["SENDER_DETAILS_REQUIRED_AT_SEND"]
    again = bridge.prepare_draft(business, receipt, root)
    assert again["reused"] is True
    assert again["fingerprint"] == result["fingerprint"]


@pytest.mark.parametrize("change,expected", [
    (lambda r: r.update(status="STALE_LIVE_STATE"), "CURRENT_SUPPORTED_REVIEW_REQUIRED"),
    (lambda r: r["row"]["judge"].update(route="CONTACT_EXCEPTION"), "CURRENT_SUPPORTED_REVIEW_REQUIRED"),
    (lambda r: r["row"]["proofer"]["checks"].update(official_domain_agrees=False), "DRAFT_PROOF_GATES_HELD"),
    (lambda r: r["row"]["proofer"].update(checks={}), "DRAFT_PROOF_GATES_HELD"),
    (lambda r: r["row"].update(company="Other company"), "DRAFT_CONTACT_IDENTITY_HELD"),
    (lambda r: r["row"]["verifier"]["selected"].update(mx_present=False), "DRAFT_CONTACT_IDENTITY_HELD"),
    (lambda r: r["row"]["verifier"]["selected"].update(verifier_version="obsolete"), "DRAFT_CONTACT_IDENTITY_HELD"),
    (lambda r: r["row"]["verifier"]["selected"].update(evidence=[]), "DRAFT_SELECTED_EVIDENCE_REQUIRED"),
])
def test_unsupported_or_mismatched_review_stays_held(proof, change, expected):
    business, receipt, root, _ = proof
    change(receipt)
    result = bridge.prepare_draft(business, receipt, root)
    assert result["status"] == "HELD"
    assert expected in result["technical_holds"]


def test_changed_capture_cannot_build_draft(proof):
    business, receipt, root, path = proof
    path.write_bytes(b"tampered")
    result = bridge.prepare_draft(business, receipt, root)
    assert result["status"] == "HELD"
    assert "DRAFT_CAPTURE_CHANGED_OR_STALE" in result["technical_holds"]


def test_old_evidence_does_not_become_current_when_review_is_fresh(proof):
    business, receipt, root, _ = proof
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    receipt["row"]["verifier"]["identity"]["page_evidence"][0]["captured_at"] = old
    assert bridge.prepare_draft(business, receipt, root)["status"] == "HELD"


def test_packet_tampering_prevents_idempotent_reuse(proof):
    business, receipt, root, _ = proof
    result = bridge.prepare_draft(business, receipt, root)
    Path(result["packet_path"]).write_text("{}")
    held = bridge.prepare_draft(business, receipt, root)
    assert "DRAFT_PACKAGE_ARTIFACT_CHANGED" in held["technical_holds"]


def test_configured_rate_and_signoff_are_bound(proof, monkeypatch):
    business, receipt, root, _ = proof
    monkeypatch.setenv("MM_HOURLY_RATE_NZD", "100")
    monkeypatch.setenv("MM_SIGN_OFF", "Dana | Acme Studio | dana@example.nz")
    result = bridge.prepare_draft(business, receipt, root)
    assert result["status"] == "DRAFT_READY"
    packet = json.loads(Path(result["packet_path"]).read_text())
    assert packet["price"]["low"]
    assert "NZ$" in packet["body"]
    assert result["technical_holds"] == []


def test_budget_failure_is_an_automatic_hold(proof):
    business, receipt, root, _ = proof
    result = bridge.prepare_draft(business, receipt, root, budget_seconds=0)
    assert result["status"] == "HELD"
    assert "DRAFT_PREPARATION_BUDGET_EXHAUSTED" in result["technical_holds"]


def test_decision_requires_exact_draft_and_permission_and_grants_no_authority(proof, monkeypatch):
    business, receipt, root, _ = proof
    monkeypatch.setenv("MM_SIGN_OFF", "Dana | Acme Studio")
    result = bridge.prepare_draft(business, receipt, root)
    packet = json.loads(Path(result["packet_path"]).read_text())
    decision = {"action": "approve", "binding": packet["decision_binding"],
                "permission_basis": "Existing customer requested this review"}
    checked = bridge.validate_decision(decision, packet)
    assert checked["valid"] is True
    assert checked["signed_approval_created"] is False
    assert checked["external_send_allowed"] is False
    changed = copy.deepcopy(decision)
    changed["binding"]["recipient"] = "other@acme.co.nz"
    assert bridge.validate_decision(changed, packet)["valid"] is False
    decision["permission_basis"] = ""
    assert "PERMISSION_BASIS_REQUIRED_WITH_APPROVAL" in bridge.validate_decision(decision, packet)["errors"]


@pytest.mark.parametrize("field,value", [("body", "changed draft"), ("recipient", "other@acme.co.nz"),
                                        ("attachments", []), ("price", {"low": "1"}),
                                        ("source_hashes", {}), ("evidence_hashes", {})])
def test_changed_packet_decision_rejected(proof, field, value):
    business, receipt, root, _ = proof
    result = bridge.prepare_draft(business, receipt, root)
    packet = json.loads(Path(result["packet_path"]).read_text())
    decision = {"action": "skip", "binding": copy.deepcopy(packet["decision_binding"])}
    packet[field] = value
    assert bridge.validate_decision(decision, packet)["valid"] is False


def test_offline_page_has_exact_draft_and_unsigned_export(proof):
    business, receipt, root, _ = proof
    result = bridge.prepare_draft(business, receipt, root)
    page = root / "approval.html"
    saved = bridge.build_approval_page([result, {"status": "HELD", "technical_holds": ["Uncertain identity"]}], page)
    text = page.read_text()
    assert saved["drafts"] == 1
    assert "connect-src 'none'" in text and "form-action 'none'" in text
    assert "Uncertain identity" in text and "info@acme.co.nz" in text
    assert "Permission basis" in text and "Download decisions" in text
    assert "fetch(" not in text
    assert "signed_approval_created:false" in text


def test_captured_fetcher_cannot_acquire_unknown_urls(proof):
    business, receipt, root, _ = proof
    _, _, captures = bridge._prove(business, receipt, root)
    client = bridge.CapturedFetcher(captures)
    assert client.get(business["public_website"]).status_code == 200
    with pytest.raises(ValueError, match="URL_NOT_IN_VERIFIED_CAPTURE_PACKET"):
        client.get("https://acme.co.nz/robots.txt")


def test_toolkit_options_are_offline_and_unknown_headers_are_not_claimed(proof, monkeypatch):
    business, receipt, root, _ = proof
    _, _, captures = bridge._prove(business, receipt, root)
    import auditor_toolkit
    report = {"run_id": "r1", "url": business["public_website"], "status": "complete",
              "defects": [{"check": "headers", "defect_key": "missing-headers"}],
              "checks": {"fetch": {"status": "ok", "required": True}, "headers": {"status": "ok", "required": True}}, "evidence": {}}
    seen = {}
    def fake_run(url, options, fetcher):
        seen.update(options=options, fetcher=fetcher)
        return copy.deepcopy(report)
    monkeypatch.setattr(auditor_toolkit, "run_audit", fake_run)
    result, method = STATIC_AUDIT(business, captures, root / "toolkit", root)
    assert method == "VERIFIED_CAPTURE_REPLAY"
    assert result["status"] == "STATIC_CAPTURE_CONTENT_ONLY"
    assert result["canonical_audit_complete"] is False
    assert result["defects"] == []
    options = seen["options"]
    assert options.browser is options.ai is options.external_tools is options.deep is options.tls is False
    assert seen["fetcher"].get(business["public_website"]).status_code == 200


def test_packet_builder_accepts_no_quote_without_changing_quoted_contract(tmp_path):
    report = {"run_id": "r", "url": "https://acme.co.nz/", "defects": []}
    remediation = build_remediation(report, tmp_path / "remediation")
    demo = build_demo(report, remediation, tmp_path / "demo", render=False)
    packet = build_packet(report, remediation, demo, None, tmp_path / "packet")
    assert packet["quote_band"] is None
    assert packet["outreach_eligible"] is False
    assert "NZ$" not in Path(packet["draft_message_path"]).read_text()


def decision_export(packet, action, *, body=None):
    return {"version": "contact-draft-intents-v1", "decisions": [{
        "action": action, "binding": packet["decision_binding"],
        "edited_body": body or packet["body"], "permission_basis": "Existing explicit permission"}]}


def test_trusted_import_is_idempotent_and_skip_survives_new_evidence(proof):
    business, receipt, root, _ = proof
    ready = bridge.prepare_draft(business, receipt, root)
    packet = json.loads(Path(ready["packet_path"]).read_text())
    exported = decision_export(packet, "skip")
    result = bridge.import_decisions(exported, [ready], root, reviewer="Human reviewer")
    assert result["external_sends"] == 0 and result["signed_approval_created"] is False
    assert result["decisions"][0]["action"] == "skip"
    assert bridge.import_decisions(exported, [ready], root, reviewer="Human reviewer")["decisions"][0]["duplicate"]
    receipt["row"]["verifier"]["selected"]["dns_checked_at"] = datetime.now(timezone.utc).isoformat()
    held = bridge.prepare_draft(business, receipt, root)
    assert held["status"] == "HELD" and held["technical_holds"] == ["DRAFT_SKIPPED_BY_USER"]


def test_edit_preserves_original_and_requires_new_exact_approval(proof):
    business, receipt, root, _ = proof
    ready = bridge.prepare_draft(business, receipt, root)
    original_bytes = Path(ready["packet_path"]).read_bytes()
    packet = json.loads(original_bytes)
    exported = decision_export(packet, "edit", body=packet["body"] + "\nAn additional human edit.\n")
    result = bridge.import_decisions(exported, [ready], root, reviewer="Human reviewer")
    chosen = result["decisions"][0]
    replacement = json.loads(Path(chosen["replacement_receipt"]).read_text())
    edited = json.loads(Path(replacement["packet_path"]).read_text())
    assert edited["fingerprint"] != packet["fingerprint"]
    assert Path(ready["packet_path"]).read_bytes() == original_bytes
    assert not bridge.validate_decision(decision_export(packet, "approve")["decisions"][0], edited)["valid"]
    assert bridge._load_packet(replacement, root)["body"] == exported["decisions"][0]["edited_body"]
    assert bridge.prepare_draft(business, receipt, root)["packet_fingerprint"] == edited["fingerprint"]


def test_approve_permission_together_records_only_exact_intent(proof, monkeypatch):
    business, receipt, root, _ = proof
    monkeypatch.setenv("MM_SIGN_OFF", "Dana | Local Studio | dana@example.nz")
    ready = bridge.prepare_draft(business, receipt, root)
    packet = json.loads(Path(ready["packet_path"]).read_text())
    result = bridge.import_decisions(decision_export(packet, "approve"), [ready], root, reviewer="Human reviewer")
    assert result["decisions"][0]["action"] == "approve"
    assert result["decisions"][0]["external_send_allowed"] is False
    assert result["signed_approval_created"] is False


def test_stale_dns_is_one_hour_and_page_holds_one_damaged_package(proof):
    business, receipt, root, _ = proof
    ready = bridge.prepare_draft(business, receipt, root)
    packet_path = Path(ready["packet_path"])
    packet = json.loads(packet_path.read_text())
    packet["dns_checked_at"] = (datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
    bridge._seal_packet(packet)
    assert "DRAFT_DNS_EVIDENCE_STALE" in bridge._current_packet_errors(packet)
    packet_path.write_text("tampered")
    page = root / "review.html"
    result = bridge.build_approval_page([ready, {"status":"HELD", "technical_holds":["Missing contact"]}], page)
    assert result["drafts"] == 0
    assert "Waiting for fresh evidence" in page.read_text() and "Missing contact" in page.read_text()


def test_owned_review_handoff_reaches_draft_without_questions(proof, monkeypatch):
    import contextlib

    import mm_contact_review_consumer as consumer
    import mm_recurring_contact_review as recurring
    business, receipt, root, _ = proof
    config = recurring.load_config()
    hashes = recurring.source_hashes()
    origin = root / "state/contact-review/runs/review"
    origin.mkdir(parents=True)
    receipt["job_directory"] = str(origin)
    recurring.atomic(origin / "1.json", receipt)
    recurring.write_manifest(origin)
    job = root / "state/contact-review/runs/draft"
    job.mkdir(parents=True)
    request = {"kind":"DRAFT_PREPARATION", "config":config,"source_hashes":hashes,
               "cases":[{"business":business,"fingerprint":recurring.fingerprint(business,hashes),"review_receipt":receipt}]}
    monkeypatch.setattr(recurring,"current_business",lambda bid:business)
    monkeypatch.setattr(recurring,"connect",lambda **kw:contextlib.nullcontext(object()))
    monkeypatch.setattr(consumer,"eligible",lambda *args:True)
    monkeypatch.setattr(recurring.signal,"alarm",lambda *args:0)
    recurring.process_draft_job(job,request)
    result = recurring.read_json(job / "RESULT.json")
    assert result["cases"][0]["status"] == "DRAFT_READY"
    assert result["external_sends"] == result["model_calls"] == result["paid_ai_cost"] == 0
    page = root / "state/contact-review/DRAFT_APPROVAL.html"
    assert "info@acme.co.nz" in page.read_text()
    assert "Approve for sending" in page.read_text()
