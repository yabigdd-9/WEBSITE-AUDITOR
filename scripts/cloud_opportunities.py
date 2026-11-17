"""Deterministic internal suitability and proposals from canonical evidence.

This adapter does not replace the local six-component campaign scorer. It maps
the bounded cloud report into the owner's requested five technical-service
dimensions. Scores are review priorities, never predictions of buying intent.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from auditor_toolkit.quote import EFFORT_HOURS, calculate_quote
from auditor_toolkit.remediation import DEFAULT_CLASS, classify

WEIGHTS = {
    "verified_technical_impact": 35, "evidence_quality": 25,
    "delivery_feasibility": 20, "business_service_fit": 15, "recency": 5,
}


def digest(document):
    return hashlib.sha256(json.dumps(
        document, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()).hexdigest()


def validate_policy(policy):
    if (
        not isinstance(policy, dict)
        or set(policy) != {"weights", "supported_defect_keys", "hourly_rate_nzd", "effort_bands"}
        or set(policy["weights"]) != set(WEIGHTS)
        or any(type(v) is not int or not 0 <= v <= 100 for v in policy["weights"].values())
        or sum(policy["weights"].values()) != 100
        or not isinstance(policy["supported_defect_keys"], list)
        or not policy["supported_defect_keys"]
        or not set(policy["supported_defect_keys"]) <= set(DEFAULT_CLASS)
        or not isinstance(policy["effort_bands"], dict)
        or not set(policy["effort_bands"]) <= set(policy["supported_defect_keys"])
        or any(band not in EFFORT_HOURS for band in policy["effort_bands"].values())
    ):
        raise ValueError("Invalid opportunity policy")
    if policy["hourly_rate_nzd"] is not None:
        rate = Decimal(str(policy["hourly_rate_nzd"]))
        if not rate.is_finite() or not 0 < rate <= 10000:
            raise ValueError("Invalid configured hourly rate")
    return policy


def load_policy(repo: Path):
    return validate_policy(json.loads((repo / "config/cloud-opportunity-policy.json").read_text()))


def score(entry, context, policy, *, now):
    validate_policy(policy)
    if not isinstance(entry, dict) or not isinstance(context, dict):
        raise ValueError("Audit entry and reviewed service context required")
    result = dict(
        status="quarantined", reason="incomplete_audit", score=None, breakdown={},
        evidence=[], buying_intent="unknown", contact_eligible=False,
        policy_sha256=digest(policy), source_run_id=entry.get("run_id"),
    )
    if context.get("suppressed") or context.get("contact_prohibited"):
        return {**result, "reason": "suppressed_or_restricted"}
    if entry.get("status") != "COMPLETE":
        return result
    from scripts.cloud_discovery import canonical_domain

    try:
        domain = canonical_domain(entry.get("domain"))
    except (ValueError, TypeError):
        return {**result, "reason": "invalid_audit_identity"}
    if not isinstance(entry.get("run_id"), str) or not entry["run_id"]:
        return {**result, "reason": "missing_audit_identity"}
    findings = entry.get("findings")
    if not isinstance(findings, list) or not findings or len(findings) > 20:
        return {**result, "reason": "no_observed_findings"}
    for finding in findings:
        if not isinstance(finding, dict):
            return {**result, "reason": "missing_or_speculative_evidence"}
        ref = finding.get("evidence_ref")
        if not (
            finding.get("confidence") == "observed"
            and finding.get("evidence_check_status") == "ok"
            and ref and ref == finding.get("evidence_check")
            and finding.get("source_url") and finding.get("observed")
            and finding.get("finding_id") and finding.get("remediation_action")
            and finding.get("severity") in {"low", "medium", "high", "critical"}
        ):
            return {**result, "reason": "missing_or_speculative_evidence"}
        try:
            if canonical_domain(finding["source_url"]) != domain:
                return {**result, "reason": "evidence_domain_mismatch"}
        except (ValueError, TypeError):
            return {**result, "reason": "invalid_evidence_url"}
        if finding.get("defect_key") not in policy["supported_defect_keys"]:
            return {**result, "reason": "unsupported_service"}
    if len({f["finding_id"] for f in findings}) != len(findings):
        return {**result, "reason": "duplicate_finding"}
    severity = {"low": 25, "medium": 50, "high": 75, "critical": 100}
    dimensions = {
        "verified_technical_impact": max(severity[f["severity"]] for f in findings),
        "evidence_quality": 100 if all(f.get("independently_verified") is True for f in findings) else 75,
    }
    reasons = dict(
        verified_technical_impact="Highest observed severity; does not establish buying intent.",
        evidence_quality="Observed canonical evidence; independent verification raises confidence.",
    )
    missing = []
    for key in ("delivery_feasibility", "business_service_fit"):
        value = context.get(key)
        if value is None:
            value = 0
            missing.append(key)
            reasons[key] = "Not configured or verified; contributes zero."
        elif type(value) is not int or not 0 <= value <= 100:
            raise ValueError("Owner service context must be 0-100 or unknown")
        else:
            reasons[key] = "Explicit reviewed service context; not customer intent."
        dimensions[key] = value
    try:
        observed = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
        age = now - observed.timestamp() if observed.tzinfo is not None else -1
    except (KeyError, TypeError, ValueError):
        age = -1
    dimensions["recency"] = 100 if 0 <= age <= 7 * 86400 else 50 if 0 <= age <= 30 * 86400 else 0
    reasons["recency"] = "Explicit evaluation time versus audit timestamp; missing/future dates contribute zero."
    breakdown = {
        key: dict(value=value, weight=policy["weights"][key],
                  contribution=float(Decimal(value) * policy["weights"][key] / 100),
                  explanation=reasons[key])
        for key, value in dimensions.items()
    }
    return {
        **result, "status": "qualified_for_internal_review", "reason": "observed_supported_work",
        "score": float(sum(Decimal(v["value"]) * v["weight"] / 100 for v in breakdown.values())),
        "breakdown": breakdown, "missing_context": missing,
        "evidence": [dict(
            finding_id=f["finding_id"], source_url=f["source_url"], evidence_ref=f["evidence_ref"],
            audit_run_id=entry.get("run_id"),
        ) for f in sorted(findings, key=lambda f: f["finding_id"])],
    }


def proposal(entry, context, policy, *, now):
    if score(entry, context, policy, now=now)["status"] != "qualified_for_internal_review":
        raise ValueError("Only evidence-qualified work can create a proposal")
    findings = sorted(entry["findings"], key=lambda f: f["finding_id"])
    items = [dict(
        finding_id=f["finding_id"], problem=f["observed"], recommendation=f["remediation_action"],
        evidence=dict(source_url=f["source_url"], check=f["evidence_ref"], run_id=entry["run_id"]),
        classification=classify(f), complexity=policy["effort_bands"].get(f["defect_key"], "Unestimated"),
        dependencies=["Owner-approved scope and authorized platform access"],
        validation_tests=["Re-run the cited canonical check and inspect the affected page."],
        limitations=["Audit observations require independent owner verification before customer use."],
    ) for f in findings]
    quote = None
    if policy["hourly_rate_nzd"] is not None and all(
        f["defect_key"] in policy["effort_bands"] for f in findings
    ):
        quote = calculate_quote(dict(
            status="complete", run_id=entry["run_id"], defects=[
                {**f, "effort_band": policy["effort_bands"][f["defect_key"]]} for f in findings
            ],
        ), policy["hourly_rate_nzd"])
    body = dict(
        kind="INTERNAL_PROPOSAL_DRAFT", business_name=context.get("business_name"),
        website=entry["domain"], source_run_id=entry["run_id"], items=items,
        deliverables=[item["recommendation"] for item in items],
        assumptions=["Client authorization, access and scope are not yet confirmed."],
        exclusions=["Production deployment", "Customer communication", "Payments", "Revenue or ranking guarantees"],
        estimated_effort=quote["estimated_hours"] if quote else None,
        pricing_status="Indicative; owner approval required" if quote else "Pricing not configured",
        pricing_inputs=dict(hourly_rate_nzd=policy["hourly_rate_nzd"], effort_bands=policy["effort_bands"]),
        indicative_quote=quote, expected_timeline="Unscheduled; scope and access require owner review.",
        acceptance_criteria=["Owner verifies cited evidence and agrees scope-specific validation."],
        approval_status="HUMAN_REVIEW_REQUIRED", binding_quote=False,
        draft_text_sha256=hashlib.sha256((entry.get("internal_scope_draft") or "").encode()).hexdigest(),
    )
    return {**body, "version_sha256": digest(body)}


def enrich(state, policy, *, now):
    validate_policy(policy)
    for prospect in state["prospects"].values():
        entry = prospect.get("audit")
        if not entry:
            continue
        context = {**prospect.get("service_context", {}), **prospect.get("discovery", {}),
                   "suppressed": prospect["status"] in {"suppressed", "removed"}}
        opportunity = score(entry, context, policy, now=now)
        if any(r["source_run_id"] == entry.get("run_id") and r["decision"] == "rejected"
               for r in prospect.get("recommendation_reviews", [])):
            opportunity.update(status="owner_rejected", reason="recorded_owner_decision", score=None)
        prospect["opportunity"] = opportunity
        if opportunity["status"] != "qualified_for_internal_review":
            prospect["proposal_version"] = None
            continue
        draft = proposal(entry, context, policy, now=now)
        versions = prospect.setdefault("proposal_versions", [])
        if not any(v["version_sha256"] == draft["version_sha256"] for v in versions):
            if len(versions) >= 100:
                raise ValueError("Proposal version capacity reached")
            versions.append(draft)
        prospect["proposal_version"] = draft["version_sha256"]


def reject_recommendation(prospect, *, actor, reason, now):
    if not isinstance(actor, str) or not actor.strip() or len(actor) > 100:
        raise ValueError("Authenticated owner identity required")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
        raise ValueError("A bounded review reason is required")
    if not (prospect.get("audit") or {}).get("run_id"):
        raise ValueError("An audited recommendation is required")
    reviews = prospect.setdefault("recommendation_reviews", [])
    if len(reviews) >= 100:
        raise ValueError("Review capacity reached")
    reviews.append(dict(
        source_run_id=prospect["audit"]["run_id"], decision="rejected", reason=reason.strip(),
        actor_sha256=hashlib.sha256(actor.encode()).hexdigest(), timestamp=now,
    ))
    prospect["proposal_version"] = None
    if prospect.get("opportunity"):
        prospect["opportunity"].update(
            status="owner_rejected", reason="recorded_owner_decision", score=None
        )
