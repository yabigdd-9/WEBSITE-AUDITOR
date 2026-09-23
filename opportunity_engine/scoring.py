"""Opportunity scoring functions."""

from __future__ import annotations

from typing import Any, Dict

def compute_opportunity_score(
    verified_need: float,
    business_value: float,
    fixability: float,
    contactability: float,
    identity_confidence: float,
    website_confidence: float,
    evidence_quality: float,
    peer_gap: float,
    market_context: float,
    expected_remediation_value: float,
    delivery_effort: float,
) -> float:
    """
    Compute opportunity score as per the core model formula.
    All inputs are expected to be in the range [0, 1].
    """
    # Avoid division by zero
    if delivery_effort == 0:
        delivery_effort = 0.001
    score = (
        verified_need
        * business_value
        * fixability
        * contactability
        * identity_confidence
        * website_confidence
        * evidence_quality
        * peer_gap
        * market_context
        * expected_remediation_value
    ) / delivery_effort
    # Clamp to [0, 1] as per the plan? The plan doesn't specify a range for the score.
    # But the bands are based on the score. We'll assume the score can be any positive number.
    # However, for simplicity, we'll return the raw score.
    return score

def score_from_opportunity(opportunity: Dict[str, Any]) -> float:
    """
    Compute opportunity score from an opportunity dictionary.
    """
    return compute_opportunity_score(
        verified_need=opportunity.get("verified_need", 0.0),
        business_value=opportunity.get("business_value", 0.0),
        fixability=opportunity.get("fixability", 0.0),
        contactability=opportunity.get("contactability", 0.0),
        identity_confidence=opportunity.get("identity_confidence", 0.0),
        website_confidence=opportunity.get("website_confidence", 0.0),
        evidence_quality=opportunity.get("evidence_quality", 0.0),
        peer_gap=opportunity.get("peer_gap", 0.0),
        market_context=opportunity.get("market_context", 0.0),
        expected_remediation_value=opportunity.get("expected_remediation_value", 0.0),
        delivery_effort=opportunity.get("delivery_effort", 0.0),
    )
