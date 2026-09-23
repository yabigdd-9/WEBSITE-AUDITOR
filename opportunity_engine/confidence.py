"""Confidence score calculation for opportunity scores."""

from __future__ import annotations

from typing import Any, Dict


def compute_confidence(
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
) -> float:
    """
    Compute confidence in the opportunity score.
    Based on completeness and reliability of input data.
    For now, return a placeholder.
    """
    # TODO: implement based on missing data, source reliability, etc.
    # Placeholder: high confidence if we have reasonable data
    confidence = 0.8  # default

    # Adjust based on available data
    if not audit_findings:
        confidence *= 0.8
    if not identity_data:
        confidence *= 0.9
    if not website_ownership_data:
        confidence *= 0.9
    if total_sources == 0:
        confidence *= 0.7
    if not signals:
        confidence *= 0.8
    if peer_count < 5:
        confidence *= 0.8

    return max(0.0, min(1.0, confidence))


def confidence_from_opportunity(opportunity: Dict[str, Any]) -> float:
    """
    Compute confidence from an opportunity dictionary.
    """
    # This would require the raw data, which we don't have in the opportunity dict.
    # For now, return a default.
    return opportunity.get("score_confidence", 0.8)