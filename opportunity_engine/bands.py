"""Opportunity bands definitions."""

from __future__ import annotations

from typing import Any, Dict

# Band thresholds (placeholder values)
# In a real implementation, these would be calibrated.
BAND_THRESHOLDS = {
    "EXECUTE_NOW": 0.8,  # score >= 0.8
    "VALIDATE_NEXT": 0.6,  # 0.6 <= score < 0.8
    "BACKLOG": 0.4,  # 0.4 <= score < 0.6
    "HOLD": 0.2,  # 0.2 <= score < 0.4
    "KILL": 0.0,  # score < 0.2
}

def get_band(score: float, confidence: float = 1.0) -> str:
    """
    Determine the opportunity band based on score and confidence.
    For now, we only use score; confidence can be used to adjust thresholds.
    """
    # Adjust thresholds based on confidence? For simplicity, we ignore confidence for now.
    if score >= BAND_THRESHOLDS["EXECUTE_NOW"]:
        return "EXECUTE_NOW"
    elif score >= BAND_THRESHOLDS["VALIDATE_NEXT"]:
        return "VALIDATE_NEXT"
    elif score >= BAND_THRESHOLDS["BACKLOG"]:
        return "BACKLOG"
    elif score >= BAND_THRESHOLDS["HOLD"]:
        return "HOLD"
    else:
        return "KILL"

def get_band_from_opportunity(opportunity: Dict[str, Any]) -> str:
    """
    Determine band from opportunity dictionary.
    """
    score = opportunity.get("score", 0.0)
    confidence = opportunity.get("score_confidence", 1.0)
    return get_band(score, confidence)
