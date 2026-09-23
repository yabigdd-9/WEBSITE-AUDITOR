"""Aggregator for opportunity features with double-counting and missing data handling."""

from __future__ import annotations

from typing import Any, Dict, List

from . import bands, features, scoring, confidence


def _group_score(feature_scores: Dict[str, float], group: List[str]) -> float:
    """Compute the average score for a group of features."""
    if not group:
        return 1.0  # neutral if no features
    valid_scores = [feature_scores[f] for f in group if f in feature_scores]
    if not valid_scores:
        return 0.0  # no data in group
    return sum(valid_scores) / len(valid_scores)


def compute_opportunity_score(
    audit_findings: List[Dict[str, Any]],
    identity_data: Dict[str, Any],
    website_ownership_data: Dict[str, Any],
    evidence_sources: List[str],
    observed_count: int,
    total_sources: int,
    finding_type: str,
    platform: str,
    affected_pages: int,
    signals: Dict[str, Any],
    technical_health: float,
    peer_median: float,
    peer_count: int,
    region: str,
    industry: str,
) -> Dict[str, Any]:
    """
    Compute opportunity score from raw data, applying double-counting controls.
    Returns a dictionary with the score, band, and feature scores.
    """
    # Compute individual feature scores
    verified_need_score = features.verified_need(audit_findings)
    identity_confidence_score = features.identity_confidence(identity_data)
    website_confidence_score = features.website_confidence(website_ownership_data)
    evidence_quality_score = features.evidence_quality(evidence_sources, observed_count, total_sources)
    fixability_score = features.fixability(finding_type, platform, affected_pages)
    delivery_effort_score = features.delivery_effort(finding_type, platform, affected_pages)
    business_value_score = features.business_value(signals)
    contactability_score = features.contactability(signals)
    peer_gap_score = features.peer_gap(technical_health, peer_median, peer_count)
    market_context_score = features.market_context(region, industry)
    expected_remediation_value_score = features.expected_remediation_value(
        finding_type, affected_pages, peer_gap_score, fixability_score
    )
    feature_scores = {
        "verified_need": verified_need_score,
        "identity_confidence": identity_confidence_score,
        "website_confidence": website_confidence_score,
        "evidence_quality": evidence_quality_score,
        "fixability": fixability_score,
        "delivery_effort": delivery_effort_score,
        "business_value": business_value_score,
        "contactability": contactability_score,
        "peer_gap": peer_gap_score,
        "market_context": market_context_score,
        "expected_remediation_value": expected_remediation_value_score,
    }

    # Define groups for numerator features (excluding delivery_effort)
    groups = {
        "technical_need": ["verified_need", "fixability", "peer_gap", "expected_remediation_value"],
        "commercial_function": ["business_value", "contactability"],
        "identity": ["identity_confidence", "website_confidence"],
        "market": ["market_context"],
        "meta": ["evidence_quality"],  # evidence_quality is a meta-feature, no double counting
    }

    # Compute group scores (average of features in group)
    group_scores = {}
    for group_name, feature_list in groups.items():
        group_scores[group_name] = _group_score(feature_scores, feature_list)

    # Compute numerator as product of group scores
    numerator = (
        group_scores["technical_need"]
        * group_scores["commercial_function"]
        * group_scores["identity"]
        * group_scores["market"]
        * group_scores["meta"]
    )

    # Avoid division by zero
    delivery_effort = feature_scores["delivery_effort"]
    if delivery_effort == 0.0:
        delivery_effort = 0.001

    # Opportunity score
    score = numerator / delivery_effort

    # Compute confidence
    conf = confidence.compute_confidence(
        audit_findings, identity_data, website_ownership_data, evidence_sources,
        observed_count, total_sources, finding_type, platform, affected_pages,
        signals, technical_health, peer_median, peer_count, region, industry
    )

    # Compute band
    band = bands.get_band(score)

    # Return results
    return {
        "score": score,
        "confidence": conf,
        "band": band,
        "feature_scores": feature_scores,
        "group_scores": group_scores,
        "numerator": numerator,
        "delivery_effort": delivery_effort,
    }


def compute_opportunity_score_from_opportunity_dict(opportunity: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute opportunity score from a pre-aggregated opportunity dictionary.
    This is for compatibility with existing code.
    """
    # Extract raw data from opportunity dictionary (assuming it has the raw data)
    # This is a placeholder; in reality, we would need to pass the raw data.
    # For now, we use the precomputed feature scores if available.
    feature_scores = {
        "verified_need": opportunity.get("verified_need", 0.0),
        "identity_confidence": opportunity.get("identity_confidence", 0.0),
        "website_confidence": opportunity.get("website_confidence", 0.0),
        "evidence_quality": opportunity.get("evidence_quality", 0.0),
        "fixability": opportunity.get("fixability", 0.0),
        "delivery_effort": opportunity.get("delivery_effort", 0.0),
        "business_value": opportunity.get("business_value", 0.0),
        "contactability": opportunity.get("contactability", 0.0),
        "peer_gap": opportunity.get("peer_gap", 0.0),
        "market_context": opportunity.get("market_context", 0.0),
        "expected_remediation_value": opportunity.get("expected_remediation_value", 0.0),
    }

    # Apply same grouping and scoring
    groups = {
        "technical_need": ["verified_need", "fixability", "peer_gap", "expected_remediation_value"],
        "commercial_function": ["business_value", "contactability"],
        "identity": ["identity_confidence", "website_confidence"],
        "market": ["market_context"],
        "meta": ["evidence_quality"],
    }

    def _group_score(fs: Dict[str, float], group: List[str]) -> float:
        valid_scores = [fs[f] for f in group if f in fs]
        if not valid_scores:
            return 0.0
        return sum(valid_scores) / len(valid_scores)

    group_scores = {}
    for group_name, feature_list in groups.items():
        group_scores[group_name] = _group_score(feature_scores, feature_list)

    numerator = (
        group_scores["technical_need"]
        * group_scores["commercial_function"]
        * group_scores["identity"]
        * group_scores["market"]
        * group_scores["meta"]
    )

    delivery_effort = feature_scores["delivery_effort"]
    if delivery_effort == 0.0:
        delivery_effort = 0.001

    score = numerator / delivery_effort
    band = bands.get_band(score)

    # Confidence is not available from the opportunity dict, so we use a default or existing field
    confidence = opportunity.get("confidence", 0.8)

    return {
        "score": score,
        "confidence": confidence,
        "band": band,
        "feature_scores": feature_scores,
        "group_scores": group_scores,
        "numerator": numerator,
        "delivery_effort": delivery_effort,
    }