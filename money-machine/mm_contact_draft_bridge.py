"""Prepare local drafts from current machine proof; never approve or send.

The supervisor rechecks live eligibility/suppression before and after this
bounded child. This bridge has no production database or transport interface.
Exported browser decisions are untrusted approval intents, never signed grants.
"""
from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import html
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from importlib.metadata import version as dependency_version
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import mm_email as email
from mm_contact_review_pathway import proofer_worker, publication_proof

VERSION = "contact-draft-bridge-v1"
SOURCE_ROOT = Path(__file__).resolve().parents[1]
PROOF_CHECKS = frozenset({
    "strict_company_identity", "exact_publication_reconfirmed", "official_domain_agrees",
    "requested_unit_agrees", "current_dns_supports_mail", "appropriate_published_purpose",
    "no_verifier_rejections", "committed_verifier_selected_high",
})
MAX_FILE_BYTES = 8 * 1024 * 1024


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _read(path):
    with Path(path).open("rb") as handle:
        raw = handle.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("DRAFT_ARTIFACT_TOO_LARGE")
    return raw


def _file_hash(path):
    return hashlib.sha256(_read(path)).hexdigest()


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(path.name + "." + str(os.getpid()) + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.chmod(0o600)
    temp.replace(path)


def _fresh(value, hours=24):
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - stamp).total_seconds()
        return 0 <= age <= hours * 3600
    except (TypeError, ValueError):
        return False


def _sources():
    # Include transitive toolkit checks/renderers, not only their entry points.
    from mm_contact_review_pathway import REQUIRED_ENGINE_FILES
    names = REQUIRED_ENGINE_FILES
    hashes = {name: _file_hash(SOURCE_ROOT / name) for name in names}
    hashes["runtime:python"] = _digest(sys.version)
    for name in ("beautifulsoup4", "httpx", "email-validator", "idna", "tldextract"):
        hashes["dependency:" + name] = _digest(dependency_version(name))
    return hashes


def _capture_path(value, receipt, runtime_root):
    path = Path(str(value))
    if path.is_absolute():
        return path.resolve()
    job = Path(str(receipt.get("job_directory", "")))
    if not job.is_absolute() or not job.resolve().is_relative_to(runtime_root / "state/contact-review/runs"):
        raise ValueError("DRAFT_CAPTURE_ROOT_UNPROVEN")
    matches = [p.resolve() for p in job.rglob(path.name) if p.is_file()
               and p.resolve().is_relative_to(job.resolve())]
    if len(matches) != 1:
        raise ValueError("DRAFT_CAPTURE_PATH_AMBIGUOUS")
    return matches[0]


def _prove(business, receipt, runtime_root):
    row = receipt.get("row") or {}
    judge = row.get("judge") or {}
    proof = row.get("proofer") or {}
    result = row.get("verifier") or {}
    selected = result.get("selected") or {}
    identity = result.get("identity") or {}
    if (receipt.get("status") != "COMPLETE" or not _fresh(receipt.get("reviewed_at"))
            or judge.get("route") != "MACHINE_SUPPORTED_RECOMMENDATION"
            or row.get("acceptance_current") is False):
        raise ValueError("CURRENT_SUPPORTED_REVIEW_REQUIRED")
    checks = proof.get("checks") or {}
    if proof.get("passed") is not True or not PROOF_CHECKS.issubset(checks) or any(v is not True for v in checks.values()):
        raise ValueError("DRAFT_PROOF_GATES_HELD")
    bid = int(business.get("live_business_id", business.get("id")))
    if (int(receipt.get("live_business_id", -1)) != bid or row.get("company") != business.get("name")
            or row.get("website") != business.get("public_website")
            or identity.get("status") != "HIGH" or selected.get("confidence_label") != "VERIFIED_HIGH"
            or selected.get("verifier_version") != email.VERSION
            or selected.get("business_match") is not True or selected.get("domain_match") is not True
            or selected.get("mx_present") is not True or selected.get("domain_accepts_mail") is not True
            or selected.get("rejection_reasons") or not _fresh(selected.get("dns_checked_at"), hours=1)):
        raise ValueError("DRAFT_CONTACT_IDENTITY_HELD")
    address, error = email.normalize_email(selected.get("email", ""))
    if error or address != selected["email"]:
        raise ValueError("EXACT_PUBLISHED_RECIPIENT_REQUIRED")
    records = identity.get("page_evidence") or []
    if not records or len(records) > 5:
        raise ValueError("DRAFT_IDENTITY_CAPTURES_REQUIRED")
    captures = []
    for record in records:
        path = _capture_path(record.get("capture_path"), receipt, runtime_root)
        raw = _read(path)
        expected = record.get("capture_hash")
        if (not _fresh(record.get("captured_at")) or not expected
                or hashlib.sha256(raw).hexdigest() != expected
                or email.root_domain(record["url"]) != email.root_domain(business["public_website"])):
            raise ValueError("DRAFT_CAPTURE_CHANGED_OR_STALE")
        meta = {"url": record["url"], "sha256": expected,
                "captured_at": record["captured_at"], "content_type": "text/html"}
        captures.append((meta, raw, path))
    sources = proof.get("sources") or []
    if not sources or any(not any(m["sha256"] == s.get("capture_sha256") and m["url"] == s.get("source_url")
                                  for m, _, _ in captures) for s in sources):
        raise ValueError("DRAFT_PUBLICATION_CAPTURE_LINK_REQUIRED")
    if not any(publication_proof(m, raw, address) for m, raw, _ in captures):
        raise ValueError("DRAFT_EXACT_PUBLICATION_REQUIRED")
    repeated = proofer_worker(business, result, [(m, raw) for m, raw, _ in captures],
                             datetime.now(timezone.utc))
    if repeated.get("passed") is not True:
        raise ValueError("DRAFT_REPEATED_PROOF_HELD")
    for record in selected.get("evidence") or []:
        path = _capture_path(record.get("capture_path"), receipt, runtime_root)
        if not _fresh(record.get("observed_at")) or _file_hash(path) != record.get("capture_hash"):
            raise ValueError("DRAFT_SELECTED_EVIDENCE_CHANGED_OR_STALE")
    if not selected.get("evidence"):
        raise ValueError("DRAFT_SELECTED_EVIDENCE_REQUIRED")
    return bid, address, captures


class CapturedFetcher:
    """No DNS/socket access: unknown URLs raise instead of inventing HTTP facts."""
    def __init__(self, captures):
        self.captures = {m["url"]: (m, raw) for m, raw, _ in captures}

    def get(self, url):
        if url not in self.captures:
            raise ValueError("URL_NOT_IN_VERIFIED_CAPTURE_PACKET")
        meta, raw = self.captures[url]
        response = httpx.Response(200, content=raw, request=httpx.Request("GET", url),
                                  headers={"content-type": meta["content_type"]})
        response.extensions["observed_at"] = meta["captured_at"]
        return response


def _saved_audit(runtime_root, business, capture_hashes):
    """Reuse only a fresh exact-site audit explicitly bound to these captures."""
    path = runtime_root / "outputs/toolkit/history.sqlite3"
    if not path.is_file():
        return None
    try:
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
            rows = db.execute("SELECT report FROM runs WHERE url=? ORDER BY timestamp DESC LIMIT 5",
                              (business["public_website"],)).fetchall()
        for raw, in rows:
            report = json.loads(raw)
            if (report.get("status") != "complete" or not _fresh(report.get("timestamp"))
                    or report.get("contact_capture_hashes") != capture_hashes
                    or report.get("contact_unit_scope") != business.get("unit_scope")):
                continue
            registered = Path(report.get("artifacts", {}).get("json", "")).resolve()
            if not registered.is_relative_to(runtime_root / "outputs/toolkit"):
                continue
            if _canonical(json.loads(_read(registered))) != _canonical(report):
                continue
            if not report.get("manifest"):
                continue
            valid = True
            for entry in report["manifest"].values():
                artifact = Path(entry["path"]).resolve()
                valid = valid and artifact.is_relative_to(registered.parent) and _file_hash(artifact) == entry["sha256"]
            if valid:
                return report
    except (OSError, ValueError, sqlite3.Error, KeyError):
        return None
    return None


def _static_audit(business, captures, output, runtime_root):
    from auditor_toolkit import AuditOptions, run_audit
    from auditor_toolkit.scoring import score_from_findings

    capture_hashes = {m["url"]: m["sha256"] for m, _, _ in captures}
    cached = _saved_audit(runtime_root, business, capture_hashes)
    if cached:
        return copy.deepcopy(cached), "HASH_BOUND_SAVED_AUDIT"
    fetcher = CapturedFetcher(captures)
    url = business["public_website"]
    if url not in fetcher.captures:
        root = email.root_domain(url)
        url = next((u for u in fetcher.captures if email.root_domain(u) == root and urlsplit(u).path in {"", "/"}), "")
    if not url:
        raise ValueError("HOME_PAGE_CAPTURE_REQUIRED_FOR_DRAFT")
    options = AuditOptions(output_root=output, profile="static", browser=False, ai=False,
                           external_tools=False, deep=False, tls=False, max_pages=1,
                           max_depth=0, max_links=1, max_bytes=MAX_FILE_BYTES, timeout=8)
    report = run_audit(url, options=options, fetcher=fetcher)
    content_checks = {name: value for name, value in report.get("checks", {}).items()
                      if name not in {"headers", "hygiene"} and value.get("required")}
    if not content_checks or any(value.get("status") != "ok" for value in content_checks.values()):
        raise ValueError("STATIC_CAPTURE_CONTENT_CHECKS_INCOMPLETE")
    # Captures do not include transport headers or robots/sitemap responses.
    # Exclude those findings; absence of saved metadata is not website failure.
    report = copy.deepcopy(report)
    report["defects"] = [d for d in report["defects"] if d.get("check") not in {"headers", "hygiene"}]
    report["status"] = "STATIC_CAPTURE_CONTENT_ONLY"
    report["canonical_audit_complete"] = False
    report["scope_limitations"] = ["HTTP headers, robots/sitemap, browser, TLS and live interactions were not measured"]
    for name in ("headers", "hygiene"):
        report["checks"][name] = {"status": "skipped", "required": False, "reason": "Original metadata unavailable"}
        report.get("evidence", {}).pop(name, None)
    breakdown = score_from_findings(report["defects"], complete=True)
    report.update(health_score=breakdown.health_score, severity_score=breakdown.severity_total,
                  defect_count=len(report["defects"]), contact_capture_hashes=capture_hashes,
                  contact_unit_scope=business.get("unit_scope"))
    return report, "VERIFIED_CAPTURE_REPLAY"


def _demo_qa(demo):
    from bs4 import BeautifulSoup

    path = Path(demo["demo_html"])
    raw = _read(path)
    soup = BeautifulSoup(raw, "html.parser")
    checks = {
        "manifest_hash_matches": hashlib.sha256(raw).hexdigest() == demo["demo_html_sha256"],
        "local_concept": demo.get("local_concept") is True,
        "no_live_change": demo.get("live_site_changed") is False,
        "no_external_deployment": demo.get("external_deploy") is False,
        "no_improvement_claim": demo.get("improvement_claim_valid") is False,
        "honest_concept_notice": "Nothing is sent" in soup.get_text() and "local demonstration" in soup.get_text(),
        "network_disabled_csp": any("connect-src 'none'" in m.get("content", "") and "form-action 'none'" in m.get("content", "")
                                    for m in soup.select("meta[http-equiv]")),
        "no_scripts_frames_forms": not soup.select("script,iframe,form"),
    }
    return {"passed": all(checks.values()), "checks": checks,
            "mode": "STATIC_LOCAL_CONCEPT_CHECK", "live_interaction_tested": False}


def _manifest_valid(directory):
    manifest = json.loads(_read(directory / "MANIFEST.json"))
    for name, expected in manifest.items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or _file_hash(path) != expected:
            raise ValueError("DRAFT_PACKAGE_ARTIFACT_CHANGED")


def _binding(packet):
    return {"packet_fingerprint": packet.get("fingerprint"), "recipient": packet.get("recipient"),
            "body": packet.get("body"), "attachments": packet.get("attachments"), "price": packet.get("price"),
            "source_hashes": packet.get("source_hashes"), "evidence_hashes": packet.get("evidence_hashes")}


def _seal_packet(packet):
    packet.pop("fingerprint", None)
    packet.pop("decision_binding", None)
    packet["fingerprint"] = _digest(packet)
    packet["decision_binding"] = _binding(packet)
    return packet


def _current_packet_errors(packet):
    failures = []
    try:
        if packet.get("source_hashes") != _sources():
            failures.append("DRAFT_IMPLEMENTATION_CHANGED")
        if not _fresh(packet.get("dns_checked_at"), hours=1):
            failures.append("DRAFT_DNS_EVIDENCE_STALE")
        if not packet.get("evidence_hashes") or not packet.get("attachments"):
            failures.append("DRAFT_PROOF_ARTIFACTS_REQUIRED")
        for path, expected_hash in packet.get("evidence_hashes", {}).items():
            if not _fresh(packet.get("evidence_observed_at", {}).get(path)) or _file_hash(path) != expected_hash:
                failures.append("DRAFT_CAPTURE_CHANGED_OR_STALE")
        for attachment in packet.get("attachments", []):
            if _file_hash(attachment["path"]) != attachment["sha256"]:
                failures.append("DRAFT_ATTACHMENT_CHANGED")
    except (OSError, KeyError, ValueError, TypeError):
        failures.append("DRAFT_ARTIFACT_UNAVAILABLE")
    return failures


def _load_packet(receipt, runtime_root=None, *, current=True):
    directory = Path(receipt["package_directory"]).resolve()
    if runtime_root is not None and not directory.is_relative_to(Path(runtime_root).resolve() / "state/contact-drafts"):
        raise ValueError("DRAFT_PACKAGE_ROOT_UNPROVEN")
    _manifest_valid(directory)
    packet_path = Path(receipt["packet_path"]).resolve()
    if not packet_path.is_relative_to(directory):
        raise ValueError("DRAFT_PACKET_PATH_ESCAPED_PACKAGE")
    packet = json.loads(_read(packet_path))
    unsigned = {k: v for k, v in packet.items() if k not in {"fingerprint", "decision_binding"}}
    if (packet.get("fingerprint") != _digest(unsigned) or packet.get("decision_binding") != _binding(packet)
            or receipt.get("packet_fingerprint") != packet.get("fingerprint")
            or packet.get("authority") != "DRAFT_ONLY" or packet.get("external_send_allowed") is not False):
        raise ValueError("DRAFT_PACKET_BINDING_CHANGED")
    if current:
        failures = _current_packet_errors(packet)
        if failures:
            raise ValueError(failures[0])
    return packet


def decision_for(receipt, runtime_root):
    """Read a local choice for this exact packet; never a production grant."""
    path = Path(runtime_root).resolve() / "state/contact-draft-decisions" / str(int(receipt["business_id"])) / (receipt["packet_fingerprint"] + ".json")
    if not path.is_file():
        return None
    result = json.loads(_read(path))
    if (result.get("packet_fingerprint") != receipt["packet_fingerprint"]
            or result.get("external_send_allowed") is not False or result.get("signed_approval_created") is not False):
        raise ValueError("DRAFT_DECISION_BINDING_CHANGED")
    return result


def _saved_draft(saved, runtime_root):
    # Decisions remain separate from immutable machine evidence packages.
    choice = decision_for(saved, runtime_root)
    if choice and choice["action"] == "edit":
        replacement = Path(choice["replacement_receipt"]).resolve()
        if not replacement.is_relative_to(runtime_root / "state/contact-drafts"):
            raise ValueError("EDITED_DRAFT_PATH_UNPROVEN")
        saved = json.loads(_read(replacement))
        choice = decision_for(saved, runtime_root)
    _load_packet(saved, runtime_root, current=not (choice and choice["action"] == "skip"))
    if choice and choice["action"] == "skip":
        return {**saved, "status": "HELD", "technical_holds": ["DRAFT_SKIPPED_BY_USER"],
                "decision_status": "SKIPPED", "reused": True}
    return {**saved, "reused": True}


def prepare_draft(business, review_receipt, runtime_root, *, budget_seconds=180):
    """Return an idempotent DRAFT_READY/HELD/ERROR receipt; no send authority.

    The owning child enforces a wall-clock deadline. This function additionally
    checks its remaining budget between local artifact stages.
    """
    runtime_root = Path(runtime_root).resolve()
    started = time.monotonic()
    receipt = {"version": VERSION, "status": "HELD", "technical_holds": [],
               "authority": "DRAFT_ONLY", "send_approval_required": True,
               "human_precision_label": None, "signed_approval_created": False,
               "production_email_writes": 0, "external_sends": 0, "model_calls": 0,
               "paid_ai_cost_usd": 0, "external_send_allowed": False}
    def budget():
        if not 0 < budget_seconds <= 300 or time.monotonic() - started >= budget_seconds:
            raise ValueError("DRAFT_PREPARATION_BUDGET_EXHAUSTED")
    try:
        budget()
        user_hold = runtime_root / "state/contact-draft-decisions" / str(int(business["live_business_id"])) / "USER_HOLD.json"
        if user_hold.is_file() and json.loads(_read(user_hold)).get("action") == "skip":
            receipt.update(business_id=business["live_business_id"], technical_holds=["DRAFT_SKIPPED_BY_USER"])
            return receipt
        bid, address, captures = _prove(business, review_receipt, runtime_root)
        source_hashes = _sources()
        rate = os.environ.get("MM_HOURLY_RATE_NZD", "").strip()
        signoff = os.environ.get("MM_SIGN_OFF", "").strip()
        basis = {"business": business, "recipient": address, "source_hashes": source_hashes,
                 "captures": [{**meta, "path": str(path)} for meta, _, path in captures],
                 "dns_checked_at": review_receipt["row"]["verifier"]["selected"]["dns_checked_at"],
                 "rate": rate, "signoff": signoff}
        key = _digest(basis)
        directory = runtime_root / "state/contact-drafts" / str(bid) / key
        receipt.update(business_id=bid, fingerprint=key, package_directory=str(directory))
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (directory / ".owner.lock").open("a") as owner:
            owner_path = directory / ".owner.lock"
            owner_path.chmod(0o600)
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            prior = directory / "RECEIPT.json"
            if prior.is_file():
                _manifest_valid(directory)
                saved = json.loads(_read(prior))
                if saved.get("fingerprint") != key:
                    raise ValueError("DRAFT_RECEIPT_FINGERPRINT_MISMATCH")
                return _saved_draft(saved, runtime_root)
            report, audit_method = _static_audit(business, captures, directory / "toolkit", runtime_root)
            budget()
            report["artifacts"] = {"json": str(directory / "audit.json")}
            report.pop("manifest", None)
            _write(directory / "audit.json", report)
            from auditor_toolkit.demo import build_demo
            from auditor_toolkit.packet import build_packet
            from auditor_toolkit.quote import calculate_quote
            from auditor_toolkit.remediation import build_remediation

            remediation = build_remediation(report, directory / "remediation")
            demo = build_demo(report, remediation, directory / "demo", render=False,
                              report_path=directory / "audit.json")
            qa = _demo_qa(demo)
            _write(directory / "qa.json", qa)
            if not qa["passed"]:
                raise ValueError("LOCAL_DEMO_QA_HELD")
            budget()
            quote = calculate_quote(report, rate) if rate else None
            packet = build_packet(report, remediation, demo, quote, directory / "message",
                                  contact={"email": address, "verification": "VERIFIED_HIGH"})
            body = _read(packet["draft_message_path"]).decode("utf-8")
            if (3 <= len(signoff) <= 200 and "\n" not in signoff
                    and not any(value in signoff.casefold() for value in ("your agency", "youragency", "[", "]"))):
                body = body.rstrip() + "\n\n" + signoff + "\n"
            else:
                receipt["technical_holds"].append("SENDER_DETAILS_REQUIRED_AT_SEND")
            packet.update(body=body, recipient=address, business_id=bid, authority="DRAFT_ONLY",
                          machine_contact_proven=True, audit_method=audit_method,
                          source_hashes=source_hashes, evidence_hashes={str(path): meta["sha256"] for meta, _, path in captures},
                          evidence_observed_at={str(path): meta["captured_at"] for meta, _, path in captures},
                          dns_checked_at=review_receipt["row"]["verifier"]["selected"]["dns_checked_at"],
                          technical_holds=list(receipt["technical_holds"]),
                          attachments=[{"path": demo["demo_html"], "sha256": _file_hash(demo["demo_html"]), "kind": "LOCAL_CONCEPT_ONLY"}],
                          price=quote.get("price_band_nzd") if quote else None,
                          quote_status="DETERMINISTIC_ESTIMATE" if quote else "NO_PRICE_INVENTED",
                          transport_mode="DISABLED", human_precision_label=None)
            packet["business"].update(name=business["name"], unit_scope=business.get("unit_scope"))
            packet["draft_message_sha256"] = hashlib.sha256(body.encode()).hexdigest()
            Path(packet["draft_message_path"]).write_text(body, encoding="utf-8")
            Path(packet["draft_message_path"]).chmod(0o600)
            _seal_packet(packet)
            budget()
            if source_hashes != _sources():
                raise ValueError("DRAFT_SOURCE_CHANGED_DURING_BUILD")
            _prove(business, review_receipt, runtime_root)
            _write(directory / "packet.json", packet)
            _write(directory / "message/packet.json", packet)
            _write(directory / "evidence.json", basis)
            receipt.update(status="DRAFT_READY", packet_path=str(directory / "packet.json"),
                           recipient=address, packet_fingerprint=packet["fingerprint"], audit_method=audit_method,
                           qa=qa, created_at=datetime.now(timezone.utc).isoformat(), reused=False)
            _write(prior, receipt)
            _write(directory / "MANIFEST.json", {str(p.relative_to(directory)): _file_hash(p)
                   for p in sorted(directory.rglob("*")) if p.is_file() and p.name not in {"MANIFEST.json", ".owner.lock"}})
            return receipt
    except BlockingIOError:
        receipt["technical_holds"].append("DRAFT_PACKAGE_ALREADY_OWNED")
    except ValueError as exc:
        receipt["technical_holds"].append(str(exc)[:200])
    except Exception as exc:
        receipt.update(status="ERROR", error=type(exc).__name__ + ": " + str(exc)[:200])
    return receipt


def validate_decision(decision, packet):
    """Validate an untrusted exported intent; creates no approval or send grant."""
    failures = []
    if not isinstance(decision, dict) or not isinstance(packet, dict):
        return {"valid": False, "errors": ["DECISION_AND_PACKET_OBJECTS_REQUIRED"], "signed_approval_created": False}
    unsigned = {k: v for k, v in packet.items() if k not in {"fingerprint", "decision_binding"}}
    if packet.get("fingerprint") != _digest(unsigned):
        failures.append("PACKET_FINGERPRINT_CHANGED")
    expected = {"packet_fingerprint": packet.get("fingerprint"), "recipient": packet.get("recipient"),
                "body": packet.get("body"), "attachments": packet.get("attachments"), "price": packet.get("price"),
                "source_hashes": packet.get("source_hashes"), "evidence_hashes": packet.get("evidence_hashes")}
    if packet.get("decision_binding") != expected or decision.get("binding") != expected:
        failures.append("EXACT_DRAFT_BINDING_MISMATCH")
    action = decision.get("action")
    if action not in {"approve", "edit", "skip"}:
        failures.append("UNSUPPORTED_DECISION_ACTION")
    if action == "approve":
        if decision.get("edited_body", packet.get("body")) != packet.get("body"):
            failures.append("EDIT_REQUIRES_NEW_PACKET_AND_APPROVAL")
        if not isinstance(decision.get("permission_basis"), str) or not decision["permission_basis"].strip():
            failures.append("PERMISSION_BASIS_REQUIRED_WITH_APPROVAL")
        if packet.get("technical_holds"):
            failures.append("TECHNICAL_HOLDS_REMAIN")
        try:
            if packet.get("source_hashes") != _sources():
                failures.append("DRAFT_IMPLEMENTATION_CHANGED")
            if not _fresh(packet.get("dns_checked_at"), hours=1):
                failures.append("DRAFT_DNS_EVIDENCE_STALE")
            for path, expected_hash in packet.get("evidence_hashes", {}).items():
                if not _fresh(packet.get("evidence_observed_at", {}).get(path)) or _file_hash(path) != expected_hash:
                    failures.append("DRAFT_CAPTURE_CHANGED_OR_STALE")
            for attachment in packet.get("attachments", []):
                if _file_hash(attachment["path"]) != attachment["sha256"]:
                    failures.append("DRAFT_ATTACHMENT_CHANGED")
        except (OSError, KeyError, ValueError):
            failures.append("DRAFT_ARTIFACT_UNAVAILABLE")
    if action == "edit" and (not isinstance(decision.get("edited_body"), str) or not 80 <= len(decision["edited_body"]) <= 20000):
        failures.append("COMPLETE_EDITED_DRAFT_REQUIRED")
    return {"valid": not failures, "errors": failures, "action": action,
             "approval_intent_only": action == "approve", "signed_approval_created": False,
             "external_send_allowed": False, "external_sends": 0}


def import_decisions(exported, receipts, runtime_root, *, reviewer):
    """Trusted local import of exact human choices; production gates still apply.

    Call only for a file the user explicitly chose to import. No watched-folder
    polling, production labels, signed grants, or sending is performed here.
    """
    runtime_root = Path(runtime_root).resolve()
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("EXPLICIT_REVIEWER_REQUIRED")
    if isinstance(exported, (str, Path)):
        exported = json.loads(_read(exported))
    if not isinstance(exported, dict) or exported.get("version") != "contact-draft-intents-v1":
        raise ValueError("DRAFT_DECISION_EXPORT_REQUIRED")
    decisions = exported.get("decisions")
    if not isinstance(decisions, list) or len(decisions) > 100:
        raise ValueError("BOUNDED_DRAFT_DECISIONS_REQUIRED")
    indexed = {r.get("packet_fingerprint"): r for r in receipts if r.get("packet_fingerprint")}
    outcomes = []
    for decision in decisions:
        try:
            original = indexed.get((decision.get("binding") or {}).get("packet_fingerprint"))
            if original is None:
                raise ValueError("EXACT_DRAFT_RECEIPT_REQUIRED")
            packet = _load_packet(original, runtime_root, current=decision.get("action") != "skip")
            validation = validate_decision(decision, packet)
            if not validation["valid"]:
                raise ValueError(";".join(validation["errors"]))
            bid = int(original["business_id"])
            folder = runtime_root / "state/contact-draft-decisions" / str(bid)
            path = folder / (packet["fingerprint"] + ".json")
            intent_hash = _digest(decision)
            if path.is_file():
                saved = json.loads(_read(path))
                if saved.get("intent_sha256") == intent_hash:
                    outcomes.append({**saved, "duplicate": True})
                    continue
                raise ValueError("PRIOR_HUMAN_CHOICE_PRESERVED")
            saved = {"action": decision["action"], "business_id": bid,
                     "packet_fingerprint": packet["fingerprint"], "binding": packet["decision_binding"],
                     "reviewer": reviewer.strip(), "permission_basis": decision.get("permission_basis"),
                     "intent_sha256": intent_hash, "recorded_at": datetime.now(timezone.utc).isoformat(),
                     "signed_approval_created": False, "external_send_allowed": False, "external_sends": 0}
            if decision["action"] == "skip":
                _write(folder / "USER_HOLD.json", saved)
                _write(runtime_root / "state/contact-review/drafts" / (str(bid) + ".json"), {
                    **original, "status": "HELD", "technical_holds": ["DRAFT_SKIPPED_BY_USER"], "decision_status": "SKIPPED"})
            elif decision["action"] == "edit":
                directory = runtime_root / "state/contact-drafts" / str(bid) / ("edit-" + intent_hash)
                directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                edited = copy.deepcopy(packet)
                edited["body"] = decision["edited_body"]
                message = directory / "draft-message.txt"
                message.write_text(edited["body"], encoding="utf-8")
                message.chmod(0o600)
                edited.update(draft_message_path=str(message),
                              draft_message_sha256=hashlib.sha256(edited["body"].encode()).hexdigest(),
                              prior_packet_fingerprint=packet["fingerprint"], exact_approval_required=True)
                _seal_packet(edited)
                _write(directory / "packet.json", edited)
                replacement = {**original, "packet_path": str(directory / "packet.json"),
                               "package_directory": str(directory), "packet_fingerprint": edited["fingerprint"],
                               "fingerprint": "edit-" + intent_hash, "reused": False,
                               "human_edited": True, "created_at": saved["recorded_at"]}
                _write(directory / "RECEIPT.json", replacement)
                _write(directory / "MANIFEST.json", {str(p.relative_to(directory)): _file_hash(p)
                       for p in sorted(directory.rglob("*")) if p.is_file() and p.name != "MANIFEST.json"})
                saved["replacement_receipt"] = str(directory / "RECEIPT.json")
                _write(runtime_root / "state/contact-review/drafts" / (str(bid) + ".json"), replacement)
            _write(path, saved)
            if decision["action"] == "approve":
                _write(runtime_root / "state/contact-review/drafts" / (str(bid) + ".json"), {
                    **original, "decision_status": "APPROVED_WAITING_FOR_SENDING_CHECKS"})
            outcomes.append(saved)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            outcomes.append({"status": "HELD", "error": str(exc)[:240], "external_sends": 0})
    return {"decisions": outcomes, "signed_approval_created": False, "external_sends": 0}


def build_approval_page(receipts, output_path):
    """One offline draft inbox; exported decisions need trusted validation."""
    cards, payloads = [], []
    for receipt in receipts:
        if receipt.get("status") != "DRAFT_READY":
            cards.append("<section><h2>Automatically held</h2><p>" + html.escape(", ".join(map(str, receipt.get("technical_holds", [])))) + "</p></section>")
            continue
        try:
            packet = _load_packet(receipt)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            cards.append("<section><h2>Waiting for fresh evidence</h2><p>" + html.escape(str(exc)) + "</p></section>")
            continue
        index = len(payloads)
        payloads.append(packet)
        def esc(value):
            return html.escape(str(value), quote=True)
        attachments = "".join("<li>" + esc(a["kind"]) + ": " + esc(a["path"]) + "<br>Hash: " + esc(a["sha256"]) + "</li>" for a in packet["attachments"])
        cards.append(f'<section data-index="{index}"><h2>Draft for {esc(packet["recipient"])}</h2>'
            + '<p>Review the finished draft here. Sending will wait for your exact approval and the final sending checks.</p>'
            + ('<p>Your exact approval is recorded. Sending checks remain pending.</p>' if receipt.get("decision_status") == "APPROVED_WAITING_FOR_SENDING_CHECKS" else '')
            + '<p>Price: ' + esc(packet["price"] or "No estimate included") + '</p><ul>' + attachments + '</ul>'
            + '<p>Technical holds: ' + esc(", ".join(packet["technical_holds"]) or "None in draft preparation; production release/send checks remain separate") + '</p>'
            + f'<label for="body-{index}">Exact draft</label><textarea id="body-{index}">' + esc(packet["body"]) + '</textarea>'
            + f'<label for="basis-{index}">Permission basis for this exact recipient</label><input id="basis-{index}" type="text">'
            + '<button data-action="approve">Approve for sending</button><button data-action="edit">Save edits</button><button data-action="skip">Skip</button>'
            + '<details><summary>Evidence and source hashes</summary><pre>' + esc(json.dumps(packet["decision_binding"], indent=2)) + '</pre></details><p class="status" aria-live="polite"></p></section>')
    data = json.dumps(payloads, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    content = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'none'; form-action 'none'; base-uri 'none'">
<title>Draft send review</title><style>body{font:17px/1.5 system-ui;max-width:1050px;margin:30px auto;padding:20px}section{border:1px solid #aab;padding:20px;margin:20px 0}textarea{display:block;width:100%;min-height:240px}input{display:block;width:95%;margin-bottom:15px}button{padding:10px;margin:8px}:focus-visible{outline:3px solid #167}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>
<h1>Draft send review</h1><p>Evidence collection and local preparation run automatically. Your decision applies only to an exact draft. Nothing is sent here.</p>
""" + "".join(cards) + "<script>const packets=" + data + ";const choices={};document.querySelectorAll('[data-action]').forEach(button=>button.addEventListener('click',()=>{const c=button.closest('section'),i=Number(c.dataset.index),p=packets[i],action=button.dataset.action,body=c.querySelector('textarea').value,basis=c.querySelector('input').value.trim();if(action==='approve'&&(body!==p.body||!basis||p.technical_holds.length)){c.querySelector('.status').textContent='Exact unchanged draft, permission basis and cleared preparation holds are required. Save edits separately.';return;}choices[i]={action,binding:p.decision_binding,edited_body:body,permission_basis:basis,approval_intent_only:true};c.querySelector('.status').textContent='Choice saved locally; nothing sent.';}));function download(){const blob=new Blob([JSON.stringify({version:'contact-draft-intents-v1',decisions:Object.values(choices),signed_approval_created:false,external_sends:0},null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='draft-decisions.json';a.click();URL.revokeObjectURL(a.href);}</script><button onclick=\"download()\">Download decisions</button></html>"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_path.write_text(content, encoding="utf-8")
    output_path.chmod(0o600)
    return {"path": str(output_path.resolve()), "sha256": _file_hash(output_path),
             "drafts": len(payloads), "signed_approval_created": False, "external_sends": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["import-decisions"])
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--reviewer", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    state = args.runtime_root.resolve() / "state/contact-review"
    receipts = [json.loads(_read(p)) for p in sorted((state / "drafts").glob("*.json"))]
    result = import_decisions(args.decisions, receipts, args.runtime_root, reviewer=args.reviewer)
    receipts = [json.loads(_read(p)) for p in sorted((state / "drafts").glob("*.json"))]
    result["page"] = build_approval_page(receipts, state / "DRAFT_APPROVAL.html")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
