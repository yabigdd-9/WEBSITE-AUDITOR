"""Deterministic internal suitability and proposals from canonical evidence.

This adapter does not replace the local six-component campaign scorer. It maps
the bounded cloud report into the owner's requested five technical-service
dimensions. Scores are review priorities, never predictions of buying intent.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from auditor_toolkit.quote import EFFORT_HOURS, calculate_quote
from auditor_toolkit.remediation import DEFAULT_CLASS, classify
from auditor_toolkit.scoring_opportunity import (
    get_opportunity_strategy,
    list_opportunity_strategies,
    register_opportunity_strategy,
)

import hashlib


def digest(document):
    """Compute SHA256 digest of JSON-serializable object."""
    return hashlib.sha256(json.dumps(
        document, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()).hexdigest()

WEIGHTS = {
    "verified_technical_impact": 35, "evidence_quality": 25,
    "delivery_feasibility": 20, "business_service_fit": 15, "recency": 5,
}


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


def score(entry, context, policy, *, now, strategy: str = "default"):
    """Score an audit entry against an opportunity policy.

    Args:
        entry: Audit entry with findings, status, run_id, etc.
        context: Service context (delivery_feasibility, business_service_fit, etc.)
        policy: Opportunity policy with weights and supported defect keys
        now: Current timestamp
        strategy: Scoring strategy name (default: "default")

    Returns:
        OpportunityResult as dict
    """
    validate_policy(policy)
    # Use strategy pattern for scoring
    scoring_strategy = get_opportunity_strategy(strategy)
    result = scoring_strategy.score(entry, context, policy, now=now)
    return {
        "status": result.status,
        "reason": result.reason,
        "score": result.score,
        "breakdown": result.breakdown,
        "missing_context": result.missing_context,
        "evidence": result.evidence,
        "buying_intent": result.buying_intent,
        "contact_eligible": result.contact_eligible,
        "policy_sha256": result.policy_sha256,
        "source_run_id": result.source_run_id,
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
