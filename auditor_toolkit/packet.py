"""P13 complete reviewable prospect packet.

This builder is intentionally incapable of sending. It binds audit evidence,
remediation previews, concept demo and deterministic quote into one hashed packet.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .common import atomic_write_json, atomic_write_text
from .proofing import build_claim_ledger, proof_draft


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bind(label: str, obj: dict) -> dict:
    """Bind only the supplied manifest object; never follow manifest-provided paths."""
    encoded = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()
    return {"kind": label, "sha256": hashlib.sha256(encoded).hexdigest()}


def _draft(report: dict, quote: dict) -> str:
    defects = report.get("defects") or []
    top = defects[0] if defects else None
    subject = "A website improvement concept"
    if top:
        finding = top.get("defect") or top.get("defect_key")
        evidence = top.get("observed") or top.get("evidence_summary") or "captured audit evidence"
        body = (
            f"I reviewed the public website at {report.get('url')} and captured one specific issue: "
            f"{finding}. The audit evidence recorded: {evidence}. "
            "I prepared a local concept showing how that area could be approached. "
        )
    else:
        body = (
            f"I reviewed the public website at {report.get('url')}. "
            "I prepared a local concept for review. "
        )
    body += (
        "The deterministic estimate is NZ$"
        + quote["price_band_nzd"]["low"]
        + "–NZ$"
        + quote["price_band_nzd"]["high"]
        + " for the currently evidenced scope. "
        + "That estimate still needs human scope/access review. "
        + "No change in traffic, enquiries, sales or revenue has been measured. "
        + "If this is not relevant, reply no thanks and there will be no follow-up."
    )
    return f"Subject: {subject}\n\n{body}\n"


def _safe_source_url(value: object) -> str | None:
    try:
        parts = urlsplit(str(value or ""))
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            return None
        # Query strings can contain tracking values or tokens; the page path is
        # enough to identify the public source without copying those values.
        return urlunsplit(("https", parts.netloc, parts.path or "/", "", ""))
    except ValueError:
        return None


def _verified_contact(contact: dict | None) -> tuple[str | None, str, dict | None]:
    """Require first-party evidence before including an email in the packet.

    Local capture paths and raw page context are deliberately excluded from the
    packet. They can contain private machine details or unrelated page content.
    """
    if not isinstance(contact, dict):
        return None, "NO_VERIFIED_EMAIL", None
    selected = contact.get("selected") or {}
    if not isinstance(selected, dict):
        return None, "NO_VERIFIED_EMAIL", None
    label = selected.get("confidence_label") or contact.get("verification")
    if label not in {"VERIFIED_HIGH", "VERIFIED"}:
        return None, str(label or "NO_VERIFIED_EMAIL"), None

    email = str(selected.get("email") or "").strip()
    provided_email = str(contact.get("email") or "").strip()
    if not email or (provided_email and provided_email.casefold() != email.casefold()):
        return None, "UNVERIFIED_MISSING_PROVENANCE", None
    if selected.get("first_party_observed") is not True:
        return None, "UNVERIFIED_MISSING_PROVENANCE", None

    evidence = selected.get("evidence")
    if not isinstance(evidence, list):
        return None, "UNVERIFIED_MISSING_PROVENANCE", None
    allowed_methods = {
        "mailto", "visible_text", "obfuscated_text", "cloudflare_obfuscation",
        "structured_data", "pdf_text",
    }
    sources = []
    seen = set()
    for item in evidence:
        if not isinstance(item, dict) or str(item.get("email", "")).casefold() != email.casefold():
            continue
        source_url = _safe_source_url(item.get("source_url"))
        digest = str(item.get("capture_hash") or "")
        observed_at = str(item.get("observed_at") or "")
        method = item.get("method")
        # This matches the evidence fields consumed by Email Finder V2. Do not
        # follow capture_path; its presence records that a capture was available.
        if (
            not source_url
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or not observed_at
            or not isinstance(method, str)
            or method not in allowed_methods
            or not item.get("capture_path")
        ):
            continue
        dedupe_key = (source_url, observed_at, method, digest)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        sources.append({
            "source_url": source_url,
            "observed_at": observed_at,
            "method": method,
            "capture_sha256": digest,
        })
    if not sources:
        return None, "UNVERIFIED_MISSING_PROVENANCE", None

    provenance = {
        "status": "VERIFIED_WITH_FIRST_PARTY_PROVENANCE",
        "confidence_label": label,
        "confidence_score": selected.get("confidence_score"),
        "verifier_version": selected.get("verifier_version") or contact.get("verifier_version"),
        "checked_at": selected.get("checked_at") or contact.get("last_checked"),
        "first_party_observed": True,
        "sources": sorted(sources, key=lambda source: (source["source_url"], source["observed_at"])),
    }
    return email, str(label), provenance


def _qa_draft(report: dict, draft: str, quote: dict) -> dict:
    result = proof_draft(draft, build_claim_ledger(report))
    errors = list(result["errors"])
    warnings = list(result["warnings"])
    if report.get("defects") and not result["referenced_claim_ids"]:
        errors.append("draft_does_not_reference_a_finding")
    if report.get("url") and str(report["url"]) not in draft:
        errors.append("draft_missing_audit_website")
    band = quote.get("price_band_nzd") or {}
    if any(not band.get(key) or str(band[key]) not in draft for key in ("low", "high")):
        errors.append("draft_missing_deterministic_quote_band")
    if "human scope/access review" not in draft:
        errors.append("draft_missing_scope_review_caveat")
    if warnings:
        errors.extend("qa_warning_requires_review:" + warning for warning in warnings)
    return {
        "passed": not errors,
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "referenced_claim_ids": result["referenced_claim_ids"],
        "unreferenced_claim_count": result["unreferenced_claim_count"],
        "human_review_required": True,
        "scope": "Deterministic claim and packet checks only; human factual, relevance and permission review remains required.",
    }


def build_packet(
    report: dict,
    remediation: dict,
    demo: dict,
    quote: dict,
    output_dir,
    *,
    contact: dict | None = None,
) -> dict:
    run_id = report.get("run_id")
    if not run_id or any(x.get("source_run_id") != run_id for x in (remediation, demo, quote)):
        raise ValueError("All packet components must bind to the same audit run")
    if demo.get("live_site_changed") is not False or demo.get("improvement_claim_valid") is not False:
        raise ValueError("Concept demo must not claim a live-site improvement")
    if quote.get("llm_determined_price") is not False:
        raise ValueError("Quote must be deterministic")

    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise ValueError("New or empty packet directory required")
    output.mkdir(parents=True, exist_ok=True)
    draft = _draft(report, quote)
    atomic_write_text(output / "draft-message.txt", draft)

    selected_email, email_state, contact_provenance = _verified_contact(contact)
    draft_qa = _qa_draft(report, draft, quote)

    packet = {
        "schema_version": 1,
        "kind": "prospect_packet",
        "source_run_id": run_id,
        "business": {"website": report.get("url"), "domain": report.get("domain")},
        "contact": selected_email,
        "email_confidence": email_state,
        "contact_provenance": contact_provenance,
        "audit_score": report.get("health_score"),
        "opportunity_score": report.get("opportunity_score"),
        "top_problems": [
            {
                "finding_id": d.get("finding_id"),
                "defect_key": d.get("defect_key"),
                "defect": d.get("defect"),
                "evidence": d.get("observed") or d.get("evidence_summary"),
            }
            for d in (report.get("defects") or [])[:5]
        ],
        "before_images": [demo["before"]] if demo.get("before") else [],
        "after_images": [demo["after"]] if demo.get("after") else [],
        "recommended_package": quote.get("package"),
        "quote_band": quote.get("price_band_nzd"),
        "proof": {
            "demo_status": demo.get("status"),
            "live_site_changed": False,
            "improvement_claim_valid": False,
        },
        "evidence": [
            _bind("audit", report),
            _bind("remediation", remediation),
            _bind("demo", demo),
            _bind("quote", quote),
        ],
        "draft_message_path": str(output / "draft-message.txt"),
        "draft_message_sha256": _sha(output / "draft-message.txt"),
        "qa_status": "PASS_HUMAN_REVIEW_REQUIRED" if draft_qa["passed"] else "FAIL_HUMAN_REVIEW_REQUIRED",
        "draft_qa": draft_qa,
        "approval_status": "HUMAN_APPROVAL_REQUIRED",
        "human_approved": False,
        "outreach_eligible": False,
        "send_enabled": False,
        "external_send_allowed": False,
        "outbound_sent": 0,
        "paid_ai_cost_usd": 0,
        "review_required": True,
    }
    atomic_write_json(output / "packet.json", packet)
    approval = (
        "# Prospect packet — HUMAN_APPROVAL_REQUIRED\n\n"
        + "Website: " + str(report.get("url")) + "\n\n"
        + "Package: " + str(quote.get("package")) + "\n\n"
        + "Quote band: NZ$" + quote["price_band_nzd"]["low"]
        + "–NZ$" + quote["price_band_nzd"]["high"] + "\n\n"
        + "The demo is a local concept only. No live-site improvement, outreach send, "
        + "deployment, payment, or paid AI call occurred.\n\n"
        + "Review packet.json, the evidence, the exact draft and contact provenance "
        + "before any external action. Automated draft checks: "
        + ("passed" if draft_qa["passed"] else "failed")
        + "; human review is still required.\n"
    )
    atomic_write_text(output / "APPROVAL_PACKET.md", approval)
    return packet
