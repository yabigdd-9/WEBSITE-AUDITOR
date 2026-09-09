"""Lead qualification integration for email pipeline.

This module integrates the qualification engine from mm_lead_qualifier.py
into the main email discovery pipeline, auto-assigning tiers (HOT, WARM, QUALIFIED, COLD)
and adding explainability layer.
"""

import re
from mm_lead_qualifier import (
    INDUSTRY_FRESHNESS_DAYS,
    INDUSTRY_WEIGHT_MULTIPLIERS,
    INDUSTRY_OFFER_MATCH,
    INDUSTRY_ALIASES,
    detect_job_signals,
    detect_budget_signals,
    industry_freshness_days,
    industry_weight_multipliers,
    industry_offer_matches,
    normalize_industry,
    qualify_lead,
    hot_lead_reasons,
    export_qualification_config,
)


# Final qualification tiers with score ranges
TIERS = {
    "HOT": 80,
    "WARM": 55,
    "QUALIFIED": 30,
    "COLD": 0,
}


def qualify_lead_with_explanation(text: str, industry: str = "", extra_signals: dict = None) -> dict:
    """Compute a qualification score for a lead with explainability.

    text: Public page text (homepage/contact/team/about pages).
    industry: Business industry (optional).
    extra_signals: Optional dict with additional signals (e.g., from operator).

    Returns a dict with:
    - qualification_score (0-100)
    - tier (HOT/WARM/QUALIFIED/COLD)
    - job_signals, budget_signals
    - industry, freshness_days, offer_matches
    - weight_multipliers
    - reasons (list of explainability factors)
    - calculated_at (timestamp)
    - basis (deterministic nature note)
    """
    return qualify_lead(text, industry, extra_signals)


def get_tier(score: float) -> str:
    """Map a score to a qualification tier."""
    if score >= TIERS["HOT"]:
        return "HOT"
    elif score >= TIERS["WARM"]:
        return "WARM"
    elif score >= TIERS["QUALIFIED"]:
        return "QUALIFIED"
    else:
        return "COLD"


def get_hot_lead_explanation(lead: dict) -> list:
    """Return the top 3 reasons a lead qualifies as HOT for operator review."""
    return hot_lead_reasons(lead)


def explain_lead_tier(lead: dict) -> str:
    """Generate a human-readable explanation of why a lead is in its tier."""
    tier = lead["tier"]
    reasons = lead.get("reasons", [])
    score = lead["qualification_score"]

    if tier == "HOT":
        return f"Lead is HOT (score {score}) because: {', '.join(reasons[:3])}"
    elif tier == "WARM":
        return f"Lead is WARM (score {score}) due to moderate signals: {', '.join(reasons[:2])}"
    elif tier == "QUALIFIED":
        return f"Lead is QUALIFIED (score {score}) with basic indicators: {', '.join(reasons[:1]) if reasons else 'No strong signals'}"
    else:
        return f"Lead is COLD (score {score}) with minimal qualifying signals"


def export_qualification_with_tiers() -> dict:
    """Return the full qualification configuration including tier thresholds."""
    config = export_qualification_config()
    config["tier_thresholds"] = TIERS
    return config


def auto_assign_tier_from_score(score: float) -> str:
    """Quick helper to assign tier based on numeric score (0-100)."""
    return get_tier(score)