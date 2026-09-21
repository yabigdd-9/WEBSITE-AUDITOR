"""P13 complete reviewable prospect packet.

This builder is intentionally incapable of sending. It binds audit evidence,
remediation previews, concept demo and deterministic quote into one hashed packet.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .common import atomic_write_json, atomic_write_text


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
        + "I have not measured or guaranteed any change in traffic, enquiries, sales or revenue. "
        + "If this is not relevant, reply no thanks and there will be no follow-up."
    )
    return f"Subject: {subject}\n\n{body}\n"


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

    selected_email = None
    email_state = "NO_VERIFIED_EMAIL"
    if contact:
        selected = contact.get("selected") or {}
        label = selected.get("confidence_label") or contact.get("verification")
        if label in {"VERIFIED_HIGH", "VERIFIED"} and contact.get("email"):
            selected_email = contact["email"]
            email_state = label

    packet = {
        "schema_version": 1,
        "kind": "prospect_packet",
        "source_run_id": run_id,
        "business": {"website": report.get("url"), "domain": report.get("domain")},
        "contact": selected_email,
        "email_confidence": email_state,
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
        "qa_status": "HUMAN_REVIEW_REQUIRED",
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
        + "before any external action.\n"
    )
    atomic_write_text(output / "APPROVAL_PACKET.md", approval)
    return packet
