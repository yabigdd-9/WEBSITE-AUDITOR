"""P13 complete reviewable prospect packet.

This builder is intentionally incapable of sending. It binds audit evidence,
remediation previews, concept demo and deterministic quote into one hashed packet.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from .common import atomic_write_json, atomic_write_text
from .opportunity import contact_provenance


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bind(label: str, obj: dict) -> dict:
    """Bind only the supplied manifest object; never follow manifest-provided paths."""
    encoded = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()
    return {"kind": label, "sha256": hashlib.sha256(encoded).hexdigest()}


def _validate_technical_qualification(report: dict, qualification_evidence: dict) -> None:
    """Replay the qualification score from this packet's complete audit findings."""
    defects = report.get("defects")
    if report.get("status") != "complete" or not isinstance(defects, list):
        raise ValueError("Complete audit findings are required for technical qualification")

    finding_ids = []
    for defect in defects:
        if not isinstance(defect, dict):
            raise ValueError("Malformed technical finding")
        severity = defect.get("severity", "medium")
        if severity not in {"low", "medium", "high", "critical"}:
            raise ValueError("Technical findings must have a valid severity")
        finding_id = defect.get("finding_id")
        if not isinstance(finding_id, str) or not finding_id.strip():
            raise ValueError("Technical findings must have stable IDs")
        finding_ids.append(finding_id)
        if severity in {"medium", "high", "critical"} and not (
            defect.get("observed")
            or defect.get("evidence_summary")
            or defect.get("evidence_ref")
            or defect.get("selector")
        ):
            raise ValueError("Material technical findings require evidence")

    if len(finding_ids) != len(set(finding_ids)):
        raise ValueError("Technical finding IDs must be unique")
    if qualification_evidence.get("technical_score_method") != "toolkit-p5-v1":
        raise ValueError("Unsupported technical score method")
    from .scoring import score_from_findings

    replayed_score = score_from_findings(defects, complete=True).severity_total
    if (
        qualification_evidence.get("technical_score_finding_ids") != finding_ids
        or qualification_evidence.get("technical_score") != replayed_score
    ):
        raise ValueError("Technical qualification does not replay from packet findings")


def _copy_demo_image(
    record: dict | None,
    name: str,
    source_name: str,
    artifact_dir: Path | None,
    output: Path,
) -> dict | None:
    if record is None:
        return None
    if not isinstance(record, dict):
        raise ValueError("Malformed demo screenshot reference")
    if artifact_dir is None:
        raise ValueError("Trusted demo_artifact_dir is required to include screenshots")
    try:
        root = Path(artifact_dir).resolve(strict=True)
        source = (root / source_name).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError("Trusted demo screenshot cannot be resolved safely") from exc
    output_parent = output.resolve().parent
    if (
        not root.is_dir()
        or root.parent != output_parent
        or source.parent != root
        or source.suffix.lower() != ".png"
        or not source.is_file()
        or source.stat().st_size > 20_000_000
        or not source.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        or record.get("sha256") != _sha(source)
    ):
        raise ValueError("Demo screenshot is outside the packet workspace or failed hash validation")
    target_dir = output / "screenshots"
    target_dir.mkdir(exist_ok=True)
    target = target_dir / name
    shutil.copyfile(source, target)
    return {"path": f"screenshots/{name}", "sha256": _sha(target), "kind": record.get("kind")}


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
    demo_artifact_dir=None,
    qualification_evidence: dict | None = None,
) -> dict:
    run_id = report.get("run_id")
    if not run_id or any(x.get("source_run_id") != run_id for x in (remediation, demo, quote)):
        raise ValueError("All packet components must bind to the same audit run")
    if demo.get("live_site_changed") is not False or demo.get("improvement_claim_valid") is not False:
        raise ValueError("Concept demo must not claim a live-site improvement")
    if quote.get("llm_determined_price") is not False:
        raise ValueError("Quote must be deterministic")

    qualification = None
    if qualification_evidence is not None:
        if not isinstance(qualification_evidence, dict):
            raise ValueError("Qualification evidence must be an object")
        if qualification_evidence.get("audit_run_id") != run_id:
            raise ValueError("Qualification evidence must bind to the same audit run")
        commercial_score = qualification_evidence.get("commercial_score")
        commercial_ids = qualification_evidence.get("commercial_score_evidence_ids")
        if (
            isinstance(commercial_score, bool)
            or not isinstance(commercial_score, (int, float))
            or not 0 <= commercial_score <= 100
            or not isinstance(commercial_ids, list)
            or not commercial_ids
            or len(commercial_ids) > 100
            or any(
                isinstance(item, bool)
                or not isinstance(item, (str, int))
                or not str(item).strip()
                for item in commercial_ids
            )
        ):
            raise ValueError("Verified commercial qualification evidence is required")
        technical_score = qualification_evidence.get("technical_score")
        technical_ids = qualification_evidence.get("technical_score_finding_ids")
        if (
            isinstance(technical_score, bool)
            or not isinstance(technical_score, (int, float))
            or not 0 <= technical_score <= 100
            or not isinstance(technical_ids, list)
            or len(technical_ids) > 100
            or any(not isinstance(item, str) or not item.strip() for item in technical_ids)
            or qualification_evidence.get("technical_score_evidence_complete") is not True
        ):
            raise ValueError("Complete technical qualification evidence is required")
        _validate_technical_qualification(report, qualification_evidence)
        qualification = {
            "audit_run_id": run_id,
            "commercial_score": commercial_score,
            "commercial_score_evidence_ids": commercial_ids,
            "commercial_score_industry": str(
                qualification_evidence.get("commercial_score_industry") or ""
            )[:200],
            "commercial_score_basis": str(
                qualification_evidence.get("commercial_score_basis") or ""
            )[:100],
            "technical_score": technical_score,
            "technical_score_method": str(
                qualification_evidence.get("technical_score_method") or ""
            )[:100],
            "technical_score_finding_ids": technical_ids,
            "technical_score_evidence_complete": True,
        }

    from .opportunity import opportunity_from_packet_evidence

    safe_contact_provenance = contact_provenance(contact)
    score_contact = contact if safe_contact_provenance else None
    packet_report = dict(report)
    if qualification is not None:
        packet_report["commercial_score"] = qualification["commercial_score"]
        packet_report["commercial_score_evidence_ids"] = qualification[
            "commercial_score_evidence_ids"
        ]
    opportunity = opportunity_from_packet_evidence(
        packet_report, remediation, quote, score_contact
    )

    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise ValueError("New or empty packet directory required")
    output.mkdir(parents=True, exist_ok=True)
    draft = _draft(report, quote)
    atomic_write_text(output / "draft-message.txt", draft)

    selected_email = None
    email_state = "NO_VERIFIED_EMAIL"
    if contact and safe_contact_provenance:
        label = safe_contact_provenance["confidence_label"]
        if label == "VERIFIED_HIGH" and contact.get("email"):
            selected_email = contact["email"]
            email_state = label
        else:
            email_state = label

    packet = {
        "schema_version": 2,
        "kind": "prospect_packet",
        "source_run_id": run_id,
        "business": {"website": report.get("url"), "domain": report.get("domain")},
        "contact": selected_email,
        "email_confidence": email_state,
        "contact_provenance": safe_contact_provenance,
        "audit_score": report.get("health_score"),
        "opportunity_score": opportunity["opportunity_score"],
        "opportunity": opportunity,
        "qualification": qualification,
        "top_problems": [
            {
                "finding_id": d.get("finding_id"),
                "defect_key": d.get("defect_key"),
                "defect": d.get("defect"),
                "evidence": d.get("observed") or d.get("evidence_summary"),
            }
            for d in (report.get("defects") or [])[:5]
        ],
        "before_images": [],
        "after_images": [],
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
        "draft_message_path": "draft-message.txt",
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
    if qualification is not None:
        packet["evidence"].append(_bind("qualification", qualification))
    trusted_demo_dir = Path(demo_artifact_dir) if demo_artifact_dir is not None else None
    before = _copy_demo_image(
        demo.get("before"), "before.png", "before-source.png", trusted_demo_dir, output
    )
    after = _copy_demo_image(
        demo.get("after"), "after.png", "concept-render.png", trusted_demo_dir, output
    )
    if before:
        packet["before_images"].append(before)
    if after:
        packet["after_images"].append(after)
    if safe_contact_provenance:
        packet["evidence"].append(_bind("contact_provenance", safe_contact_provenance))
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
