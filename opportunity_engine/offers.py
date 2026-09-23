"""Offer family mapping for opportunity intelligence."""

from __future__ import annotations

from typing import Any, Dict, List


def _average(scores: list[float]) -> float:
    """Return the average of a list of scores, ignoring empty lists."""
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def map_to_offer_family(opportunity: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map opportunity to primary and secondary offer families.
    Uses feature scores to determine the most relevant offer family.
    """
    feature_scores = opportunity.get("feature_scores", {})
    if not feature_scores:
        # Fallback to opportunity score if feature scores not available
        score = opportunity.get("score", 0.0)
        if score >= 0.8:
            return {"primary_offer_family": "technical_health", "secondary_offer_family": [], "evidence": {}}
        elif score >= 0.6:
            return {"primary_offer_family": "commercial_performance", "secondary_offer_family": [], "evidence": {}}
        else:
            return {"primary_offer_family": "general_consulting", "secondary_offer_family": [], "evidence": {}}

    # Compute group scores (same as in aggregator)
    technical_need = _average([
        feature_scores.get("verified_need", 0.0),
        feature_scores.get("fixability", 0.0),
        feature_scores.get("peer_gap", 0.0),
        feature_scores.get("expected_remediation_value", 0.0),
    ])
    commercial_function = _average([
        feature_scores.get("business_value", 0.0),
        feature_scores.get("contactability", 0.0),
    ])
    identity = _average([
        feature_scores.get("identity_confidence", 0.0),
        feature_scores.get("website_confidence", 0.0),
    ])
    market = feature_scores.get("market_context", 0.0)
    evidence_quality = feature_scores.get("evidence_quality", 0.0)

    # Determine primary offer family
    if technical_need > 0.6 and technical_need >= commercial_function and technical_need >= identity:
        primary = "technical_health"
        secondary = []
        if commercial_function > 0.4:
            secondary.append("commercial_performance")
        if identity < 0.4:
            secondary.append("identity_verification")
    elif commercial_function > 0.6 and commercial_function >= technical_need and commercial_function >= identity:
        primary = "commercial_performance"
        secondary = []
        if technical_need > 0.4:
            secondary.append("technical_health")
        if identity < 0.4:
            secondary.append("identity_verification")
    elif identity < 0.4:
        primary = "identity_verification"
        secondary = []
        if technical_need > 0.6:
            secondary.append("technical_health")
        if commercial_function > 0.6:
            secondary.append("commercial_performance")
    elif market > 0.6:
        primary = "market_expansion"
        secondary = []
        if technical_need > 0.4:
            secondary.append("technical_health")
        if commercial_function > 0.4:
            secondary.append("commercial_performance")
    else:
        primary = "general_consulting"
        secondary = []
        if technical_need > 0.6:
            secondary.append("technical_health")
        if commercial_function > 0.6:
            secondary.append("commercial_performance")
        if identity < 0.4:
            secondary.append("identity_verification")

    # Remove duplicates and limit secondary to two
    secondary = list(dict.fromkeys(secondary))[:2]

    evidence = {
        "technical_need": technical_need,
        "commercial_function": commercial_function,
        "identity": identity,
        "market": market,
        "evidence_quality": evidence_quality,
    }

    return {
        "primary_offer_family": primary,
        "secondary_offer_family": secondary,
        "evidence": evidence,
    }