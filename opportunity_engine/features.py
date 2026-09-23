"""Feature implementations for opportunity scoring."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def verified_need(audit_findings: List[Dict[str, Any]]) -> float:
    """
    Compute verified_need score from audit findings.
    Evidence of a real, material problem that affects the website's function,
    security, performance, or compliance.
    """
    if not audit_findings:
        return 0.0

    # Map impact to weight
    impact_weights = {
        "CRITICAL": 1.0,
        "HIGH": 0.8,
        "MEDIUM": 0.5,
        "LOW": 0.2,
    }

    total_weight = 0.0
    for finding in audit_findings:
        impact = finding.get("impact", "LOW")
        weight = impact_weights.get(impact, 0.2)
        total_weight += weight

    # Normalize: assume 3 findings of CRITICAL (weight 1.0 each) saturates at 1.0
    verified_need = min(1.0, total_weight / 3.0)
    return verified_need


def identity_confidence(identity_data: Dict[str, Any]) -> float:
    """
    Compute identity confidence from identity engine data.
    Confidence that the business identity is correct and the website belongs to that business.
    """
    # Try to extract confidence from known keys
    for key in ("confidence", "score", "identity_confidence"):
        if key in identity_data:
            val = identity_data[key]
            if isinstance(val, (int, float)):
                return max(0.0, min(1.0, float(val)))
    # Default if no confidence data
    return 0.5


def website_confidence(website_ownership_data: Dict[str, Any]) -> float:
    """
    Compute website confidence from website ownership engine data.
    Confidence that the website ownership is credible and the business owns the website.
    """
    # Same logic as identity_confidence
    for key in ("confidence", "score", "website_confidence"):
        if key in website_ownership_data:
            val = website_ownership_data[key]
            if isinstance(val, (int, float)):
                return max(0.0, min(1.0, float(val)))
    return 0.5


def evidence_quality(evidence_sources: List[str], observed_count: int, total_sources: int) -> float:
    """
    Compute evidence quality score.
    Quality of evidence supporting the opportunity score.
    """
    if total_sources == 0:
        return 0.0
    observed_ratio = observed_count / total_sources
    if observed_ratio >= 0.8:
        if observed_count >= 2:
            return 1.0  # observed_multi_source
        else:
            return 0.9  # observed_single_source
    elif observed_ratio >= 0.5:
        return 0.7      # strong_inference
    else:
        return 0.4      # heuristic


def fixability(finding_type: str, platform: str, affected_pages: int) -> float:
    """
    Compute fixability score.
    Whether WEBSITE-AUDITOR can produce a practical, testable remediation for the problem.
    """
    high_fixability = {
        "meta/title issue",
        "broken CTA",
        "missing structured data",
        "large image optimization",
        "broken internal link",
        "simple configuration issue",
    }
    medium_fixability = {
        "theme performance",
        "complex internal-link restructure",
        "large template refactor",
    }
    low_fixability = {
        "complete platform migration",
        "unknown proprietary CMS",
        "major backend replacement",
    }

    if finding_type in high_fixability:
        return 0.9
    elif finding_type in medium_fixability:
        return 0.6
    elif finding_type in low_fixability:
        return 0.3
    else:
        # Default to medium if unknown
        return 0.5


def delivery_effort(finding_type: str, platform: str, affected_pages: int) -> float:
    """
    Return delivery effort band normalized to [0,1] (XS=0.0, S=0.25, M=0.5, L=0.75, XL=1.0).
    Estimated relative implementation effort without pretending the estimate is a fixed quote.
    """
    # Base effort by finding type
    xl_types = {
        "complete platform migration",
        "unknown proprietary CMS",
        "major backend replacement",
    }
    l_types = {
        "theme performance",
        "complex internal-link restructure",
        "large template refactor",
    }
    xs_types = {
        "meta/title issue",
        "broken CTA",
        "missing structured data",
        "large image optimization",
        "broken internal link",
        "simple configuration issue",
    }

    if finding_type in xl_types:
        band = "XL"
    elif finding_type in l_types:
        band = "L"
    elif finding_type in xs_types:
        band = "XS"
    else:
        band = "M"  # default medium

    # Adjust by affected pages
    if affected_pages > 10:
        # Increase effort by one band (but not above XL)
        if band == "XS":
            band = "S"
        elif band == "S":
            band = "M"
        elif band == "M":
            band = "L"
        elif band == "L":
            band = "XL"
    elif affected_pages > 1:
        # Increase effort by half a band (simplified: one step)
        if band == "XS":
            band = "S"
        elif band == "S":
            band = "M"
        elif band == "M":
            band = "L"
        elif band == "L":
            band = "XL"

    # Map band to float
    band_to_float = {
        "XS": 0.0,
        "S": 0.25,
        "M": 0.5,
        "L": 0.75,
        "XL": 1.0,
        "UNKNOWN": 0.0,
    }
    return band_to_float.get(band, 0.5)


def business_value(signals: Dict[str, Any]) -> float:
    """
    Return business value category normalized to [0,1] (LOW=0.0, MEDIUM=0.5, HIGH=1.0).
    Estimate whether the website appears commercially important to the business.
    """
    if not signals:
        return 0.0  # UNKNOWN treated as LOW per missing_behavior

    score = 0.0
    # Commercial signals
    if signals.get("ecommerce"):
        score += 0.4
    if signals.get("booking_functionality"):
        score += 0.3
    if signals.get("quote_request_functionality"):
        score += 0.3
    if signals.get("lead_generation_ctas"):
        score += 0.2
    if signals.get("service_business_dependence_on_enquiries"):
        score += 0.2
    loc_count = signals.get("number_of_locations", 0)
    if isinstance(loc_count, (int, float)) and loc_count > 1:
        score += 0.2

    score = min(1.0, score)

    # Map to categories
    if score < 0.33:
        return 0.0   # LOW
    elif score < 0.66:
        return 0.5   # MEDIUM
    else:
        return 1.0   # HIGH


def contactability(signals: Dict[str, Any]) -> float:
    """
    Measure whether legitimate business contact paths are available.
    """
    if not signals:
        return 0.0

    score = 0.0
    strong = [
        "verified_first_party_business_email",
        "official_contact_form",
        "verified_business_phone",
    ]
    medium = [
        "business_social_contact",
        "public_inquiry_page",
    ]
    weak = [
        "unverified_guessed_email",
        "catch_all_only",
    ]

    for key in strong:
        if signals.get(key):
            score += 0.4
    for key in medium:
        if signals.get(key):
            score += 0.2
    for key in weak:
        if signals.get(key):
            score += 0.1

    return min(1.0, score)


def peer_gap(technical_health: float, peer_median: float, peer_count: int) -> float:
    """
    Compute peer gap score (percentile).
    Measure how far the website differs from relevant nearby/category peers.
    """
    if peer_count < 5:
        return 0.0  # insufficient data -> missing_behavior: remove_contribution
    if technical_health < peer_median:
        gap = (peer_median - technical_health) / peer_median
        return min(1.0, gap)  # normalize to [0,1]
    return 0.0  # better than or equal to median -> no gap


def market_context(region: str, industry: str) -> float:
    """
    Return market context strength normalized to [0,1] (LOW_CONTEXT=0.0, MEDIUM_CONTEXT=0.5, HIGH_CONTEXT=1.0).
    Provide industry and regional context without pretending public market statistics reveal an individual company's buying intent.
    """
    # Placeholder: return MEDIUM_CONTEXT
    # In reality, would use region/industry to lookup contextual data
    return 0.5


def expected_remediation_value(finding_type: str, affected_pages: int, peer_gap: float, fixability: float) -> float:
    """
    Compute expected remediation value.
    Estimated value of remediating the problem (e.g., increased conversion, reduced risk).
    """
    # Early stage: combine scope, peer gap, fixability
    # Assume scope is proportion of pages affected [0,1] - we use affected_pages as a placeholder
    # We'll normalize affected_pages by assuming a typical site has 100 pages
    scope = min(1.0, affected_pages / 100.0)
    value = scope * peer_gap * fixability
    return min(1.0, value)