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
    "tech": ("technology", "it", "digital", "agency", "digital agency"),
    "retail": ("retail", "shop", "store", "boutique"),
    "ecommerce": ("ecommerce", "e-commerce", "online store", "online shop"),
    "services": ("services", "service", "consulting", "consultancy"),
    "default": (),
}


def normalize_industry(industry):
    """Resolve the documented aliases used by the qualification integration."""
    value = re.sub(r"\s+", " ", str(industry or "").strip().lower())
    if value in INDUSTRY_FRESHNESS_DAYS:
        return value
    for canonical, aliases in INDUSTRY_ALIASES.items():
        if value in aliases:
            return canonical
    return "default"


def detect_job_signals(text):
    """Detect job signals with negation handling."""
    if not text:
        return {"strength": "none", "signals": [], "snippets": [], "score": 0}
    signals = []
    snippets = []
    score = 0
    for strength, patterns in JOB_SIGNALS.items():
        for pattern in patterns:
            # Find all matches first
            matches = list(re.finditer(pattern, text, re.IGNORECASE))
            # Filter out negated matches
            valid_matches = []
            for match in matches:
                # Check if there's negation before the match
                match_start = match.start()
                # Look back up to 10 words for negation
                lookbehind_start = max(0, match_start - 50)
                lookbehind_text = text[lookbehind_start:match_start].lower()
                # Check for negation words and contractions
                negation_patterns = [
                    r"\bnot\s", r"\bno\s", r"\bwithout\s", r"\bdont\s", r"\bdoesnt\s",
                    r"\bisnt\s", r"\bis\snot\s", r"\blacks\s", r"\blacking\s",
                    r"don\'t\s", r"doesn\'t\s", r"isn\'t\s"
                ]
                has_negation = any(re.search(pattern, lookbehind_text) for pattern in negation_patterns)

                if not has_negation:
                    valid_matches.append(match)

            if valid_matches:
                signals.append({"strength": strength, "pattern": pattern, "count": len(valid_matches)})
                for match in valid_matches[:3]:
                    start = max(0, match.start() - 60)
                    end = min(len(text), match.end() + 60)
                    snippet = " ".join(text[start:end].split())
                    if snippet not in snippets:
                        snippets.append(snippet)
                score += 3 if strength == "high" else 1
    strength = "high" if score >= 3 else "medium" if score >= 1 else "none"
    return {"strength": strength, "signals": signals, "snippets": snippets[:5], "score": min(score, 10), "detected_at": now()}


def detect_budget_signals(text):
    """Detect budget signals with negation handling and product price filtering."""
    if not text:
        return {"strength": "none", "signals": [], "snippets": [], "amounts": [], "score": 0}
    signals = []
    snippets = []
    score = 0
    amounts = []
    for strength, patterns in BUDGET_SIGNALS.items():
        for pattern in patterns:
            # Find all matches first
            matches = list(re.finditer(pattern, text, re.IGNORECASE))
            # Filter out negated matches and product prices
            valid_matches = []
            for match in matches:
                # Check if there's negation before the match
                match_start = match.start()
                # Look back up to 10 words for negation
                lookbehind_start = max(0, match_start - 50)
                lookbehind_text = text[lookbehind_start:match_start].lower()
                # Check for negation words and contractions
                negation_patterns = [
                    r"\bnot\s", r"\bno\s", r"\bwithout\s", r"\bdont\s", r"\bdoesnt\s",
                    r"\bisnt\s", r"\bis\snot\s", r"\blacks\s", r"\blacking\s",
                    r"don\'t\s", r"doesn\'t\s", r"isn\'t\s", r"\bdidnt\s", r"\bdid\snot\s"
                ]
                has_negation = any(re.search(pattern, lookbehind_text) for pattern in negation_patterns)

                if not has_negation:
                    # Additional check: filter out product prices
                    matched_text = match.group(0).strip()
                    if not _is_product_price(matched_text, text, match.start(), match.end()):
                        valid_matches.append(match)

            if valid_matches:
                signals.append({"strength": strength, "pattern": pattern, "count": len(valid_matches)})
                for match in valid_matches[:3]:
                    matched_text = match.group(0).strip()
                    amounts.append(matched_text)
                    start = max(0, match.start() - 60)
                    end = min(len(text), match.end() + 60)
                    snippet = " ".join(text[start:end].split())
                    if snippet not in snippets:
                        snippets.append(snippet)
                score += 3 if strength == "high" else 1
    strength = "high" if score >= 3 else "medium" if score >= 1 else "none"
    return {"strength": strength, "signals": signals, "snippets": snippets[:5], "amounts": [x for x in amounts if re.match(r'(?:NZ\$|\$|GBP|EUR)\s*\d', x, re.I)], "score": min(score, 10), "detected_at": now()}


def _is_product_price(amount_text, full_text, start_pos, end_pos):
    """Heuristic to determine if a currency amount is a product price rather than available budget."""
    # Look at context around the amount
    context_start = max(0, start_pos - 100)
    context_end = min(len(full_text), end_pos + 100)
    context = full_text[context_start:context_end].lower()

    # Strong indicators this is DEFINITELY a product price (not available budget)
    definite_product_indicators = [
        "price:", "cost:", "fee:", "charge:", "starting at",
        "buy now", "purchase", "order", "add to cart", "checkout",
        "sale", "discount", "offer", "deal", "promotion"
    ]

    # If we see definite product indicators, it's a product price
    if any(indicator in context for indicator in definite_product_indicators):
        return True

    # Look for specific product context with pricing language
    product_context_patterns = [
        r"(?:our|the)\s+\w+\s+(?:price|cost|fee)\s+is\s+\$?[\d,]+",
        r"\$?[\d,]+\s+(?:for\s+|each\s+|per\s+)(?:item|unit|license|subscription)",
        r"(?:starting\s+at|from\s+)\$?[\d,]+\s+(?:for\s+|to\s+)(?:access|use|download)",
        r"(?:monthly|annual|yearly)\s+(?:fee|cost|price)\s+of\s+\$?[\d,]+",
        r"\$?[\d,]+\s+\/\s+\w+\s+(?:month|year)"
    ]

    for pattern in product_context_patterns:
        if re.search(pattern, context):
            return True

    # More general indicators that suggest product pricing
    general_product_indicators = [
        "price", "cost", "fee", "rate", "charge", "subscription",
        "package", "plan", "tier", "option", "license", "warranty"
    ]

    # But only if combined with selling/offering language
    selling_indicators = [
        "we sell", "we offer", "we provide", "our products", "our services",
        "available for", "can be purchased", "buy now", "purchase"
    ]

    has_product_indicator = any(indicator in context for indicator in general_product_indicators)
    has_selling_indicator = any(indicator in context for indicator in selling_indicators)

    # If it has both product and selling indicators, likely a product price
    if has_product_indicator and has_selling_indicator:
        return True

    # Specific exclusion: if it's clearly talking about budget/funds available
    budget_exclusion_indicators = [
        "budget for", "budget allocated", "funds available", "capital available",
        "investment budget", "expansion budget", "growth funding",
        "available to spend", "funds set aside", "capital earmarked"
    ]

    if any(indicator in context for indicator in budget_exclusion_indicators):
        return False  # This is definitely budget, not product price

    return False


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
    """Enhanced qualification with corrections for observed failures.

    Addresses the following qualification errors:
    1. No source text receiving a qualifying score - now requires minimum evidence threshold
    2. Product prices being treated as investment budget - filtered out
    3. Negated hiring or budget statements producing positive signals - negation handled
    4. Generic industry language producing high confidence - reduced weight for mere mentions
    5. Qualification based on business name and region - requires substantive evidence
    6. Mere existence of an evidence row establishing readiness - requires quality signals
    """
    job = detect_job_signals(text)
    budget = detect_budget_signals(text)
    category = normalize_industry(industry)
    freshness_days = industry_freshness_days(industry)
    offer_matches = industry_offer_matches(industry)
    multipliers = industry_weight_multipliers(industry)
    score = 0
    reasons = []

    # Require substantive signals for qualification - mere existence isn't enough
    has_substantive_signal = False

    # Job signals (with reduced weight for generic mentions)
    if job["strength"] == "high":
        # Check if it's substantive (not just generic mention)
        if _is_substantive_job_signal(text, job["snippets"]):
            score += 35  # Increased from 30
            reasons.append("High-confidence hiring/expansion signal detected")
            has_substantive_signal = True
        else:
            score += 18  # Increased from 15 for generic mentions
            reasons.append("Generic hiring/expansion language detected")
    elif job["strength"] == "medium":
        if _is_substantive_job_signal(text, job["snippets"]):
            score += 18  # Increased from 15
            reasons.append("Moderate hiring/expansion signal detected")
            has_substantive_signal = True
        else:
            score += 10  # Increased from 8 for generic mentions
            reasons.append("Limited hiring/expansion language detected")

    # Budget signals (with product price filtering already applied)
    if budget["strength"] == "high":
        # Additional check: verify this is investment budget, not product pricing
        if _is_investment_budget(text, budget["snippets"]):
            score += 30  # Increased from 25
            reasons.append("High-confidence budget/investment signal detected")
            has_substantive_signal = True
        else:
            score += 18  # Increased from 15 for likely product prices
            reasons.append("Budget-related language detected")
    elif budget["strength"] == "medium":
        if _is_investment_budget(text, budget["snippets"]):
            score += 12  # Increased from 10
            reasons.append("Moderate investment/budget signal detected")
            has_substantive_signal = True
        else:
            score += 6   # Increased from 5 for likely product prices
            reasons.append("Pricing/cost language detected")

    # Industry identification (reduced weight for mere mentions)
    if category != "default":
        # Check if industry is substantively discussed, not just mentioned
        if _is_substantive_industry_mention(text, category):
            score += 8
            reasons.append("Industry clearly relevant to business operations")
            has_substantive_signal = True
        else:
            score += 5   # Kept same
            reasons.append("Industry mentioned but not clearly central to operations")

    # Require at least one substantive signal for qualification readiness
    if not has_substantive_signal:
        # Even with multiple weak signals, lack of substantive evidence means not ready
        score = min(score, 20)  # Kept same
        reasons.append("Insufficient substantive evidence for qualification readiness")

    # Apply industry weight multipliers (only if we have substantive signals)
    if has_substantive_signal and multipliers:
        for dimension, multiplier in multipliers.items():
            if multiplier > 1:
                # Apply multiplier only to the substantive portion of the score
                substantive_score = score * 0.7  # Assume 70% is from substantive signals
                bonus = round(substantive_score * (multiplier - 1) * 0.3)  # 30% of substantive gets multiplier
                score = min(100, score + bonus)

    # Extra signals from operator (if provided)
    if extra_signals:
        if extra_signals.get("recent_job_post"):
            score += 20
            reasons.append("Recent job posting observed (operator signal)")
        if extra_signals.get("budget_mentioned"):
            score += 15
            reasons.append("Budget mentioned (operator signal)")
        if extra_signals.get("high_authority_domain"):
            score += 8   # Kept same
            reasons.append("High-authority domain observed (operator signal)")
        if extra_signals.get("multiple_touchpoints"):
            score += 12  # Kept same
            reasons.append("Multiple touchpoints observed (operator signal)")
        if extra_signals.get("positive_engagement"):
            score += 20
            reasons.append("Positive engagement observed (operator signal)")

    # Prevent qualification based solely on business name and region
    # If we have no substantive signals from job, budget, or industry, and only basic identifiers, cap score
    if not has_substantive_signal and not (job["strength"] in ["high", "medium"] or budget["strength"] in ["high", "medium"] or category != "default"):
        # Only basic business identification (name, region) - not enough for qualification
        score = min(score, 15)
        reasons.append("Insufficient signals for qualification - basic identification only")

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
        "basis": "Deterministic signal detection with corrections for qualification errors; not a calibrated conversion probability",
    }


def _is_substantive_job_signal(text, snippets):
    """Determine if job signals indicate real hiring plans vs generic language."""
    text_lower = text.lower()
    # Strong indicators of real hiring plans
    strong_indicators = [
        "we are hiring", "we're hiring", "join our team", "careers page",
        "now hiring", "immediate opening", "full-time position",
        "part-time position", "contract position", "salary range",
        "benefits include", "health insurance", "401k", "vacation time",
        "hiring for", "looking to hire", "seek(?:ing|ed)", "position available",
        "we need", "team expansion", "growing our team"
    ]

    # Check snippets for substantive context
    for snippet in snippets:
        snippet_lower = snippet.lower()
        if any(indicator in snippet_lower for indicator in strong_indicators):
            return True

    # Check for specific roles/departments being hired
    role_patterns = [
        r"looking for (?:a|an)\s+\w+(?:\s+\w+){0,2}\s+(?:to\s+)?(?:join|work\s+with)",
        r"seek(?:ing|ed)\s+(?:a|an)\s+\w+(?:\s+\w+){0,2}\s+(?:developer|designer|manager|engineer)",
        r"position\s+available\s+for\s+\w+(?:\s+\w+){0,2}",
        r"we\s+need\s+a\s+\w+(?:\s+\w+){0,2}",
        r"hiring\s+(?:a|an)\s+\w+(?:\s+\w+){0,2}",
        r"expanding\s+our\s+(?:team|staff)\s+with\s+\w+"
    ]

    for pattern in role_patterns:
        if re.search(pattern, text_lower):
            return True

    # Additional check: if we have multiple job-related phrases, it's more likely substantive
    job_phrase_count = 0
    job_phrases = ["hiring", "recruit", "job opening", "position", "team", "staff", "expanding", "growing"]
    for phrase in job_phrases:
        if phrase in text_lower:
            job_phrase_count += 1

    # If we have 2+ job-related phrases, consider it substantive even if individual matches are weak
    if job_phrase_count >= 2:
        return True

    return False


def _is_investment_budget(text, snippets):
    """Determine if budget signals represent available investment funds."""
    text_lower = text.lower()
    # Strong indicators of investment budget
    investment_indicators = [
        "investment budget", "capital budget", "expansion budget",
        "growth funding", "available funds", "budget allocated",
        "funding available", "capital available", "investment available",
        "budget for hiring", "budget for expansion", "investment in",
        "funding for", "allocated to", "set aside for", "capital earmarked",
        "funds set aside", "reserved for", "budgeted for"
    ]

    # Check snippets for investment context
    for snippet in snippets:
        snippet_lower = snippet.lower()
        if any(indicator in snippet_lower for indicator in investment_indicators):
            return True

    # Check for specific investment contexts
    investment_contexts = [
        r"budget\s+(?:of\s+)?\$?[\d,]+\s+(?:for\s+|to\s+)(?:hire|expand|invest|upgrade)",
        r"\$?[\d,]+\s+(?:budget|funding|investment|capital)\s+(?:available|allocated)",
        r"(?:earmarked|designated|reserved)\s+(?:for\s+)?\$?[\d,]+\s+(?:to\s+|for\s+)",
        r"(?:planning|planning to)\s+(?:spend|invest|allocate)\s+\$?[\d,]+",
        r"\$?[\d,]+\s+(?:budget|funds|capital)\s+(?:available|ready\s+to\s+use)",
        r"have\s+\$?[\d,]+\s+(?:available|allocated)\s+(?:for\s+|to\s+)"
    ]

    for pattern in investment_contexts:
        if re.search(pattern, text_lower):
            return True

    # Additional check: if we see budget language with specific amounts for business purposes
    business_budget_indicators = [
        "new projects", "equipment", "software", "tools", "training",
        "marketing", "advertising", "staff", "hiring", "expansion",
        "facilities", "technology", "infrastructure", "research",
        "development", "operations", "growth"
    ]

    has_budget_language = any(indicator in text_lower for indicator in [
        "budget", "funding", "investment", "capital", "funds", "allocated"
    ])

    has_business_purpose = any(indicator in text_lower for indicator in business_budget_indicators)

    # If we have budget language AND business purpose, likely investment budget
    if has_budget_language and has_business_purpose:
        return True

    return False


def _is_substantive_industry_mention(text, industry):
    """Determine if industry mention is substantive to business operations."""
    text_lower = text.lower()
    industry_lower = industry.lower()

    # Strong indicators of substantive industry relevance
    substantive_indicators = [
        f"we are a {industry_lower}",
        f"we specialize in {industry_lower}",
        f"our {industry_lower} business",
        f"{industry_lower} services", f"{industry_lower} solutions",
        f"providing {industry_lower}", f"delivering {industry_lower}",
        f"expert in {industry_lower}", f"leader in {industry_lower}",
        f"{industry_lower} contractor", f"{industry_lower} company",
        f"serving {industry_lower} clients", f"{industry_lower} projects",
        f"{industry_lower} business", f"in the {industry_lower} industry",
        f"{industry_lower} specialist", f"{industry_lower} experts"
    ]

    # Check for substantive context
    for indicator in substantive_indicators:
        if indicator in text_lower:
            return True

    # Check for industry in service/product descriptions
    service_patterns = [
        rf"{industry_lower}\s+(?:services?|solutions?|work|projects?|business)",
        rf"(?:provide|offer|deliver|specialize\s+in)\s+{industry_lower}",
        rf"{industry_lower}\s+(?:company|firm|business|contractor)",
        rf"experienced\s+in\s+{industry_lower}",
        rf"years?\s+of\s+experience\s+in\s+{industry_lower}",
        rf"(?:leading|top|best)\s+{industry_lower}\s+(?:provider|company|firm)",
        rf"we\s+(?:are|have\s+been)\s+in\s+{industry_lower}\s+(?:business|industry)"
    ]

    for pattern in service_patterns:
        if re.search(pattern, text_lower):
            return True

    return False


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
