"""Deterministic decision intelligence for prioritising website-audit work.

This module answers one narrow question: what should happen next, and why?
It does not send outreach, change pipeline state, set prices, or call an LLM.
Unknown/weak evidence lowers confidence and routes work to review.
"""
from __future__ import annotations

DECISION_VERSION = "decision-v1"

WEIGHTS = {
    "technical_opportunity": 0.20,
    "commercial_opportunity": 0.20,
    "identity_confidence": 0.15,
    "evidence_confidence": 0.15,
    "evidence_freshness": 0.10,
    "contactability": 0.05,
    "conversion_path_health": 0.10,
    "delivery_feasibility": 0.05,
}


def _unit(name: str, value: float) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric from 0 to 1")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric from 0 to 1") from exc
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return number


def priority_decision(
    *,
    technical_opportunity: float,
    commercial_opportunity: float,
    identity_confidence: float,
    evidence_confidence: float,
    evidence_freshness: float,
    contactability: float,
    conversion_path_health: float,
    estimated_effort: float,
) -> dict:
    """Return a reproducible priority, confidence, blockers and next action.

    Scores are additive so a missing contact does not erase a strong technical
    opportunity. Low-confidence identity/evidence is never promoted into an
    automatic action: it becomes a blocker and routes to verification/review.
    """
    values = {
        "technical_opportunity": _unit("technical_opportunity", technical_opportunity),
        "commercial_opportunity": _unit("commercial_opportunity", commercial_opportunity),
        "identity_confidence": _unit("identity_confidence", identity_confidence),
        "evidence_confidence": _unit("evidence_confidence", evidence_confidence),
        "evidence_freshness": _unit("evidence_freshness", evidence_freshness),
        "contactability": _unit("contactability", contactability),
        "conversion_path_health": _unit("conversion_path_health", conversion_path_health),
        "estimated_effort": _unit("estimated_effort", estimated_effort),
    }
    weighted = {
        "technical_opportunity": values["technical_opportunity"] * WEIGHTS["technical_opportunity"],
        "commercial_opportunity": values["commercial_opportunity"] * WEIGHTS["commercial_opportunity"],
        "identity_confidence": values["identity_confidence"] * WEIGHTS["identity_confidence"],
        "evidence_confidence": values["evidence_confidence"] * WEIGHTS["evidence_confidence"],
        "evidence_freshness": values["evidence_freshness"] * WEIGHTS["evidence_freshness"],
        "contactability": values["contactability"] * WEIGHTS["contactability"],
        "conversion_path_health": values["conversion_path_health"] * WEIGHTS["conversion_path_health"],
        "delivery_feasibility": (1.0 - values["estimated_effort"]) * WEIGHTS["delivery_feasibility"],
    }
    priority_score = round(sum(weighted.values()) * 100.0, 1)
    confidence = round(
        (
            values["evidence_confidence"] * 0.40
            + values["identity_confidence"] * 0.35
            + values["evidence_freshness"] * 0.25
        ),
        3,
    )

    reasons: list[str] = []
    if values["technical_opportunity"] >= 0.70:
        reasons.append("HIGH_TECHNICAL_NEED")
    if values["commercial_opportunity"] >= 0.70:
        reasons.append("STRONG_COMMERCIAL_FIT")
    if values["identity_confidence"] >= 0.80:
        reasons.append("STRONG_IDENTITY")
    if values["evidence_confidence"] >= 0.80 and values["evidence_freshness"] >= 0.70:
        reasons.append("FRESH_STRONG_EVIDENCE")
    if values["conversion_path_health"] < 0.50:
        reasons.append("CONVERSION_PATH_WEAK")
    if values["contactability"] >= 0.70:
        reasons.append("CONTACT_VERIFIED")
    if values["estimated_effort"] <= 0.35:
        reasons.append("LOW_DELIVERY_EFFORT")

    blockers: list[str] = []
    if values["identity_confidence"] < 0.60:
        blockers.append("IDENTITY_NOT_CONFIRMED")
    if values["evidence_confidence"] < 0.60:
        blockers.append("EVIDENCE_CONFIDENCE_LOW")
    if values["evidence_freshness"] < 0.50:
        blockers.append("EVIDENCE_STALE")
    if values["conversion_path_health"] < 0.50:
        blockers.append("CONVERSION_PATH_NEEDS_REVIEW")
    if values["contactability"] < 0.40:
        blockers.append("NO_VERIFIED_CONTACT")

    if "IDENTITY_NOT_CONFIRMED" in blockers:
        next_action = "VERIFY_IDENTITY"
    elif "EVIDENCE_CONFIDENCE_LOW" in blockers or "EVIDENCE_STALE" in blockers:
        next_action = "VERIFY_EVIDENCE"
    elif "CONVERSION_PATH_NEEDS_REVIEW" in blockers:
        next_action = "INVESTIGATE_FLOW"
    elif "NO_VERIFIED_CONTACT" in blockers:
        next_action = "VERIFY_CONTACT"
    elif priority_score >= 65.0 and confidence >= 0.70:
        next_action = "BUILD_DEMO"
    elif priority_score >= 40.0:
        next_action = "HUMAN_REVIEW"
    else:
        next_action = "HOLD"

    return {
        "formula_version": DECISION_VERSION,
        "priority_score": priority_score,
        "confidence": confidence,
        "reason_codes": reasons,
        "blockers": blockers,
        "next_action": next_action,
        "components": values,
        "weighted_components": {k: round(v * 100.0, 2) for k, v in weighted.items()},
        "human_review_required": True,
        "side_effects": "none",
    }
