"""Opportunity review packet generation."""

from __future__ import annotations

from typing import Any, Dict, List

from . import offers


def create_review_packet(opportunity: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a human review packet for the opportunity.
    """
    feature_scores = opportunity.get("feature_scores", {})
    group_scores = opportunity.get("group_scores", {})
    score = opportunity.get("score", 0.0)
    confidence = opportunity.get("confidence", 0.0)
    band = opportunity.get("band", "KILL")

    # Identity section
    identity = {
        "identity_confidence": feature_scores.get("identity_confidence", 0.0),
        "website_confidence": feature_scores.get("website_confidence", 0.0),
        "identity_score": group_scores.get("identity", 0.0),
    }

    # Problem section (technical need)
    problem = {
        "verified_need": feature_scores.get("verified_need", 0.0),
        "expected_remediation_value": feature_scores.get("expected_remediation_value", 0.0),
        "fixability": feature_scores.get("fixability", 0.0),
        "peer_gap": feature_scores.get("peer_gap", 0.0),
        "technical_need_score": group_scores.get("technical_need", 0.0),
    }

    # Commercial section
    commercial = {
        "business_value": feature_scores.get("business_value", 0.0),
        "contactability": feature_scores.get("contactability", 0.0),
        "commercial_function_score": group_scores.get("commercial_function", 0.0),
    }

    # Contact section (we already have contactability in commercial, but we keep for clarity)
    contact = {
        "contactability": feature_scores.get("contactability", 0.0),
    }

    # Offer section
    offer = offers.map_to_offer_family(opportunity)

    # Proof section
    proof = {
        "evidence_quality": feature_scores.get("evidence_quality", 0.0),
        "confidence": confidence,
        "evidence_quality_score": group_scores.get("meta", 0.0),
    }

    # Limitations section
    limitations = {
        "missing_features": [],  # TODO: track missing data
        "warnings": [],
    }
    if confidence < 0.6:
        limitations["warnings"].append("Low confidence in opportunity score")
    if score < 0.2:
        limitations["warnings"].append("Opportunity score is very low (KILL band)")

    return {
        "identity": identity,
        "problem": problem,
        "commercial": commercial,
        "contact": contact,
        "offer": offer,
        "proof": proof,
        "limitations": limitations,
        "overall_score": score,
        "band": band,
    }