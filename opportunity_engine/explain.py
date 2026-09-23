"""Opportunity score explanations."""

from __future__ import annotations

from typing import Any, Dict, List

from . import bands


def explain_score(opportunity: Dict[str, Any]) -> Dict[str, Any]:
    """
    Explain how the opportunity score was computed.
    Returns a dictionary with detailed explanation.
    """
    feature_scores = opportunity.get("feature_scores", {})
    if not feature_scores:
        return {
            "feature_contributions": {},
            "group_scores": {},
            "delivery_effort": 0.0,
            "score": opportunity.get("score", 0.0),
            "band": opportunity.get("band", "KILL"),
            "missing_features": [],
            "score_version": "1.0.0",
            "explanation_text": "Insufficient data to explain score.",
        }

    # Compute group scores (same as in aggregator)
    def _average(scores: list[float]) -> float:
        if not scores:
            return 0.0
        return sum(scores) / len(scores)

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
    delivery_effort = feature_scores.get("delivery_effort", 0.0)

    # Avoid division by zero
    if delivery_effort == 0.0:
        delivery_effort = 0.001

    score = (technical_need * commercial_function * identity * market * evidence_quality) / delivery_effort
    band = bands.get_band(score)

    # Feature contributions: we can show how much each group contributes to the numerator
    numerator = technical_need * commercial_function * identity * market * evidence_quality
    # Avoid division by zero in contribution calculation
    if numerator == 0.0:
        contrib_technical_need = 0.0
        contrib_commercial_function = 0.0
        contrib_identity = 0.0
        contrib_market = 0.0
        contrib_evidence_quality = 0.0
    else:
        contrib_technical_need = technical_need * commercial_function * identity * market * evidence_quality / numerator if technical_need != 0 else 0.0
        # Actually, the contribution of each group is multiplicative, so we can't easily split.
        # Instead, we show the group scores and let the user see the product.
        # We'll just show the group scores and the delivery_effort.
        contrib_technical_need = technical_need
        contrib_commercial_function = commercial_function
        contrib_identity = identity
        contrib_market = market
        contrib_evidence_quality = evidence_quality

    explanation_text = (
        f"Opportunity score of {score:.3f} (band: {band}) is driven by:\n"
        f"- Technical need group: {technical_need:.3f}\n"
        f"- Commercial function group: {commercial_function:.3f}\n"
        f"- Identity group: {identity:.3f}\n"
        f"- Market context: {market:.3f}\n"
        f"- Evidence quality: {evidence_quality:.3f}\n"
        f"Divided by delivery effort: {delivery_effort:.3f}."
    )

    return {
        "feature_contributions": {
            "verified_need": feature_scores.get("verified_need", 0.0),
            "fixability": feature_scores.get("fixability", 0.0),
            "peer_gap": feature_scores.get("peer_gap", 0.0),
            "expected_remediation_value": feature_scores.get("expected_remediation_value", 0.0),
            "business_value": feature_scores.get("business_value", 0.0),
            "contactability": feature_scores.get("contactability", 0.0),
            "identity_confidence": feature_scores.get("identity_confidence", 0.0),
            "website_confidence": feature_scores.get("website_confidence", 0.0),
            "market_context": feature_scores.get("market_context", 0.0),
            "evidence_quality": feature_scores.get("evidence_quality", 0.0),
            "delivery_effort": delivery_effort,
        },
        "group_scores": {
            "technical_need": technical_need,
            "commercial_function": commercial_function,
            "identity": identity,
            "market": market,
            "evidence_quality": evidence_quality,
        },
        "delivery_effort": delivery_effort,
        "score": score,
        "band": band,
        "missing_features": [],  # TODO: track missing data
        "score_version": "1.0.0",
        "explanation_text": explanation_text,
    }