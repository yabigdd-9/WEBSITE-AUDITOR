"""Explainable, review-oriented prospect ranking.

A high score means "worth human review", never a sales/outcome prediction.
"""
from __future__ import annotations

from typing import Any


CONTACT_POINTS = {"high": 15, "medium": 9, "low": 3, "none": 0, "": 0}
INTENT_POINTS = {"high": 15, "medium": 9, "low": 3, "": 0}


def _number(record: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        value = record.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        try:
            if value not in (None, ""):
                return float(value)
        except (TypeError, ValueError):
            continue
    return default


def rank_prospect(record: dict[str, Any]) -> dict[str, Any]:
    opportunity = max(0.0, min(100.0, _number(record, "opportunity_score", "score")))
    quick_wins = max(0.0, _number(record, "quick_win_count", "quick_wins"))
    critical = max(0.0, _number(record, "critical_defects"))
    high = max(0.0, _number(record, "high_defects"))
    finding_count = max(0.0, _number(record, "finding_count", "defect_count"))
    contact_confidence = str(record.get("contact_confidence") or "").lower()
    commercial_intent = str(record.get("commercial_intent") or "").lower()

    components = {
        "opportunity_evidence": round(opportunity * 0.35, 2),
        "quick_wins": min(20.0, quick_wins * 5.0),
        "severity": min(15.0, critical * 6.0 + high * 2.0),
        "finding_depth": min(10.0, finding_count * 0.75),
        "contact_confidence": float(CONTACT_POINTS.get(contact_confidence, 0)),
        "commercial_intent": float(INTENT_POINTS.get(commercial_intent, 0)),
    }
    score = round(min(100.0, sum(components.values())), 2)

    if score >= 70:
        tier = "HOT"
    elif score >= 50:
        tier = "WARM"
    elif score >= 25:
        tier = "NURTURE"
    else:
        tier = "COLD"

    explanation = [
        f"{name.replace('_', ' ')}: +{value:g}"
        for name, value in components.items()
        if value > 0
    ]
    return {
        "review_score": score,
        "tier": tier,
        "components": components,
        "explanation": explanation,
        "meaning": "priority for human review; not a sale/conversion prediction",
    }
