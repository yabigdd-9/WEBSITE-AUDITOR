"""Opportunity schema definition."""

from __future__ import annotations

from typing import Any, List

# Opportunity schema fields as defined in the plan
OPPORTUNITY_SCHEMA = {
    "opportunity_id": str,
    "business_id": str,
    "website_id": str,
    "audit_run_id": str,
    "top_finding_ids": List[str],
    "verified_need": str,  # could be enum: LOW, MEDIUM, HIGH
    "identity_confidence": float,  # 0.0-1.0
    "website_confidence": float,  # 0.0-1.0
    "evidence_quality": str,  # could be enum: observed_multi_source, observed_single_source, strong_inference, heuristic, unsupported
    "fixability": float,  # 0.0-1.0
    "delivery_effort": str,  # bands: XS, S, M, L, XL, UNKNOWN
    "business_value": str,  # categories: LOW, MEDIUM, HIGH, UNKNOWN
    "contactability": float,  # 0.0-1.0
    "peer_gap": float,  # percentile 0.0-1.0
    "peer_count": int,
    "market_context": str,  # strength: LOW_CONTEXT, MEDIUM_CONTEXT, HIGH_CONTEXT
    "expected_remediation_value": float,
    "proofability": float,  # 0.0-1.0
    "score": float,  # opportunity score
    "score_confidence": float,  # 0.0-1.0
    "band": str,  # EXECUTE_NOW, VALIDATE_NEXT, BACKLOG, HOLD, KILL
    "primary_offer_family": str,
    "blocking_reasons": List[str],
    "missing_features": List[str],
    "model_version": str,
    "created_at": str,  # ISO timestamp
    "updated_at": str,  # ISO timestamp
}

def validate_opportunity(opportunity: dict[str, Any]) -> list[str]:
    """Validate opportunity against schema, return list of errors."""
    errors = []
    for field, expected_type in OPPORTUNITY_SCHEMA.items():
        if field not in opportunity:
            errors.append(f"Missing required field: {field}")
            continue
        value = opportunity[field]
        if expected_type == list:
            if not isinstance(value, list):
                errors.append(f"Field {field} must be a list")
        elif expected_type == str:
            if not isinstance(value, str):
                errors.append(f"Field {field} must be a string")
        elif expected_type == float:
            if not isinstance(value, (float, int)):
                errors.append(f"Field {field} must be a number")
        elif expected_type == int:
            if not isinstance(value, int):
                errors.append(f"Field {field} must be an integer")
        # Note: we could add more specific validation for enums, ranges, etc.
    return errors
