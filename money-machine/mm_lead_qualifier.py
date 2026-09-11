"""Lead qualification engine: job signals, budget signals, and qualification scoring.

This module adds intelligence to prospect discovery by detecting:
- Job signals (hiring, recruiting, expansion announcements)
- Budget signals (currency amounts, project sizes, investment language)
- Industry-aware qualification scoring

All signals are deterministic and evidence-based. No model calls are made.
"""
import datetime as dt
import json
import re
from pathlib import Path

from mm_core import now, sha


# Industry-aware freshness windows (days)
INDUSTRY_FRESHNESS_DAYS = {
    "construction": 14,
    "services": 14,
    "plumbing": 14,
    "electrical": 14,
    "hvac": 14,
    "saas": 3,
    "software": 3,
    "tech": 3,
    "retail": 7,
    "ecommerce": 7,
        "default": 7,
}

# Job signal keywords (grouped by signal strength)
JOB_SIGNALS = {
    "high": [
        r"\b(hiring|recruit(?:ing|er|ment)|job(?:s| openings?)|careers?|vacancies?|positions? open)\b",
        r"\b(expand(?:ing|ed|s)?|growth|growing|scale(?:ing|d)?)\b",
    ],
    "medium": [
        r"\b(team|staff|crew|workforce)\b",
        r"\b(new|open|launch(?:ed|ing)?|opening)\b",
    ],
}

# Budget signal keywords and currency patterns
BUDGET_SIGNALS = {
    "high": [
        r"(\$|NZ\$|GBP|EUR)\s*[0-9][0-9,]*(?:\.[0-9]{1,2})?\s*(?:k|m|thousand|million|billion)?",
        r"\b(?:budget|investment|funding|allocated|spend|price range|estimated cost)\b",
    ],
        "medium": [
        r"\b(?:quote|estimate|pricing|cost|price|fee)\b",
    ],
}

# Industry-specific offer mapping (problem -> confidence boost)
INDUSTRY_OFFER_MATCH = {
    "construction": ("quoting", "booking", "follow_up"),
    "plumbing": ("quoting", "booking", "follow_up"),
    "electrical": ("quoting", "booking", "follow_up"),
    "hvac": ("quoting", "booking", "follow_up"),
    "saas": ("lead_capture", "crm", "reporting"),
    "software": ("lead_capture", "crm", "reporting"),
    "tech": ("lead_capture", "crm", "reporting"),
    "retail": ("lead_capture", "booking", "crm"),
    "ecommerce": ("lead_capture", "booking", "crm"),
    "default": ("lead_capture", "follow_up", "crm"),
}

# Industry-specific weight adjustments (dimension -> multiplier)
INDUSTRY_WEIGHT_MULTIPLIERS = {
    "construction": {"ability_to_pay": 1.5, "urgency": 1.2, "decision_access": 1.1},
    "plumbing": {"ability_to_pay": 1.5, "urgency": 1.2, "decision_access": 1.1},
    "electrical": {"ability_to_pay": 1.5, "urgency": 1.2, "decision_access": 1.1},
    "hvac": {"ability_to_pay": 1.5, "urgency": 1.2, "decision_access": 1.1},
    "saas": {"pain": 1.2, "fit": 1.3, "demoability": 1.3},
    "software": {"pain": 1.2, "fit": 1.3, "demoability": 1.3},
    "tech": {"pain": 1.2, "fit": 1.3, "demoability": 1.3},
    "retail": {"pain": 1.1, "fit": 1.2, "upsell": 1.3},
    "ecommerce": {"pain": 1.1, "fit": 1.2, "upsell": 1.3},
    "default": {},
}

# Industry aliases (normalize business industry names)
INDUSTRY_ALIASES = {
    "construction": ("construction", "building", "builder", "renovation", "renovations", "contractor", "contractors"),
    "plumbing": ("plumbing", "plumber", "plumbers"),
    "electrical": ("electrical", "electrician", "electricians", "electric"),
    "hvac": ("hvac", "heating", "cooling", "ventilation", "air conditioning", "heat pump", "climate control"),
    "saas": ("saas", "software as a service"),
    "software": ("software", "app", "application", "web development", "web design"),
    "tech": ("technology", "it", "digital", "agency"),
    "retail": ("retail", "shop", "store", "boutique"),
    "ecommerce": ("ecommerce", "e-commerce", "online store", "online shop"),
    "services": ("services", "service", "consulting", "consultancy"),
    "default": (),
}


def detect_job_signals(text):
    if not text:
        return {"strength": "none", "signals": [], "snippets": [], "score": 0}
    signals = []
    snippets = []
    score = 0
    for strength, patterns in JOB_SIGNALS.items():
        for pattern in patterns:
            matches = list(re.finditer(pattern, text, re.IGNORECASE))
            if matches:
                signals.append({"strength": strength, "pattern": pattern, "count": len(matches)})
                for match in matches[:3]:
                    start = max(0, match.start() - 60)
                    end = min(len(text), match.end() + 60)
                    snippet = " ".join(text[start:end].split())
                    if snippet not in snippets:
                        snippets.append(snippet)
                score += 3 if strength == "high" else 1
    strength = "high" if score >= 3 else "medium" if score >= 1 else "none"
    return {"strength": strength, "signals": signals, "snippets": snippets[:5], "score": min(score, 10), "detected_at": now()}


def detect_budget_signals(text):
    if not text:
        return {"strength": "none", "signals": [], "snippets": [], "score": 0}
    signals = []
    snippets = []
    score = 0
    amounts = []
    for strength, patterns in BUDGET_SIGNALS.items():
        for pattern in patterns:
            matches = list(re.finditer(pattern, text, re.IGNORECASE))
            if matches:
                signals.append({"strength": strength, "pattern": pattern, "count": len(matches)})
                for match in matches[:3]:
                    matched_text = match.group(0).strip()
                    amounts.append(matched_text)
                    start = max(0, match.start() - 60)
                    end = min(len(text), match.end() + 60)
                    snippet = " ".join(text[start:end].split())
                    if snippet not in snippets:
                        snippets.append(snippet)
                score += 3 if strength == "high" else 1
    strength = "high" if score >= 3 else "medium" if score >= 1 else "none"
    return {"strength": strength, "signals": signals, "snippets": snippets[:5], "score": min(score, 10), "detected_at": now()}


def industry_freshness_days(industry):
    category = normalize_industry(industry)
    return INDUSTRY_FRESHNESS_DAYS.get(category, INDUSTRY_FRESHNESS_DAYS["default"])


def industry_weight_multipliers(industry):
    category = normalize_industry(industry)
    return INDUSTRY_WEIGHT_MULTIPLIERS.get(category, INDUSTRY_WEIGHT_MULTIPLIERS["default"])


def industry_offer_matches(industry):
    category = normalize_industry(industry)
    return INDUSTRY_OFFER_MATCH.get(category, INDUSTRY_OFFER_MATCH["default"])


def qualify_lead(text, industry="", extra_signals=None):
    job = detect_job_signals(text)
    budget = detect_budget_signals(text)
    category = normalize_industry(industry)
    freshness_days = industry_freshness_days(industry)
    offer_matches = industry_offer_matches(industry)
    multipliers = industry_weight_multipliers(industry)
    score = 0
    reasons = []
    if job["strength"] == "high":
        score += 35
        reasons.append("High-confidence hiring/expansion signal detected")
    elif job["strength"] == "medium":
        score += 15
        reasons.append("Medium-confidence team/growth signal detected")
    if budget["strength"] == "high":
        score += 30
        reasons.append("High-confidence budget/investment signal detected")
    elif budget["strength"] == "medium":
        score += 10
        reasons.append("Medium-confidence pricing/cost signal detected")
    if category != "default":
        score += 10
        reasons.append("Industry category identified: " + category)
    if multipliers:
        for dimension, multiplier in multipliers.items():
            if multiplier > 1:
                score = min(100, score + round(5 * (multiplier - 1) * 10))
    if extra_signals:
        if extra_signals.get("recent_job_post"):
            score += 20
            reasons.append("Recent job posting observed (operator signal)")
        if extra_signals.get("budget_mentioned"):
            score += 15
            reasons.append("Budget mentioned (operator signal)")
        if extra_signals.get("high_authority_domain"):
            score += 10
            reasons.append("High-authority domain observed (operator signal)")
        if extra_signals.get("multiple_touchpoints"):
            score += 15
            reasons.append("Multiple touchpoints observed (operator signal)")
        if extra_signals.get("positive_engagement"):
            score += 20
            reasons.append("Positive engagement observed (operator signal)")
    score = min(100, max(0, score))
    if score >= 80:
        tier = "HOT"
    elif score >= 55:
        tier = "WARM"
    elif score >= 30:
        tier = "QUALIFIED"
    else:
        tier = "COLD"
    return {
        "qualification_score": score,
        "tier": tier,
        "job_signals": job,
        "budget_signals": budget,
        "industry": category,
        "freshness_days": freshness_days,
        "offer_matches": offer_matches,
        "weight_multipliers": multipliers,
        "reasons": reasons,
        "calculated_at": now(),
        "basis": "Deterministic signal detection; not a calibrated conversion probability",
    }


def hot_lead_reasons(lead):
    if lead.get("tier") != "HOT":
        return []
    return lead.get("reasons", [])[:3]


def export_qualification_config():
    return {
        "industry_freshness_days": INDUSTRY_FRESHNESS_DAYS,
        "industry_weight_multipliers": INDUSTRY_WEIGHT_MULTIPLIERS,
        "industry_offer_matches": INDUSTRY_OFFER_MATCH,
        "job_signal_keywords": JOB_SIGNALS,
        "budget_signal_keywords": BUDGET_SIGNALS,
    }
    return {"strength": strength, "signals": signals, "snippets": snippets[:5], "amounts": list(dict.fromkeys(amounts))[:10], "score": min(score, 10), "detected_at": now()}