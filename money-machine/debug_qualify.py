import sys
import mm_lead_qualifier as q

def debug_qualify_lead(text, industry="", extra_signals=None):
    """Debug version of qualify_lead with print statements."""
    print(f"=== DEBUG QUALIFY_LEAD ===")
    print(f"Input: text='{text}', industry='{industry}', extra_signals={extra_signals}")
    
    job = q.detect_job_signals(text)
    budget = q.detect_budget_signals(text)
    category = q.normalize_industry(industry)
    freshness_days = q.industry_freshness_days(industry)
    offer_matches = q.industry_offer_matches(industry)
    multipliers = q.industry_weight_multipliers(industry)
    print(f"Job signals: {job}")
    print(f"Budget signals: {budget}")
    print(f"Category: {category}")
    print(f"Multipliers: {multipliers}")
    
    score = 0
    reasons = []
    has_substantive_signal = False
    
    print(f"\n--- Initial ---")
    print(f"score: {score}, has_substantive_signal: {has_substantive_signal}")
    
    # Job signals
    if job["strength"] == "high":
        if q._is_substantive_job_signal(text, job["snippets"]):
            score += 35
            reasons.append("Substantive hiring/expansion signal detected")
            has_substantive_signal = True
            print(f"-> HIGH SUBSTANTIVE JOB: score={score}, has_substantive_signal={has_substantive_signal}")
        else:
            score += 18
            reasons.append("Generic hiring/expansion language detected")
            print(f"-> HIGH GENERIC JOB: score={score}")
    elif job["strength"] == "medium":
        if q._is_substantive_job_signal(text, job["snippets"]):
            score += 18
            reasons.append("Moderate hiring/expansion signal detected")
            has_substantive_signal = True
            print(f"-> MEDIUM SUBSTANTIVE JOB: score={score}, has_substantive_signal={has_substantive_signal}")
        else:
            score += 10
            reasons.append("Limited hiring/expansion language detected")
            print(f"-> MEDIUM GENERIC JOB: score={score}")

    # Budget signals
    if budget["strength"] == "high":
        if q._is_investment_budget(text, budget["snippets"]):
            score += 30
            reasons.append("Substantive investment/budget signal detected")
            has_substantive_signal = True
            print(f"-> HIGH SUBSTANTIVE BUDGET: score={score}, has_substantive_signal={has_substantive_signal}")
        else:
            score += 18
            reasons.append("Budget-related language detected")
            print(f"-> HIGH GENERIC BUDGET: score={score}")
    elif budget["strength"] == "medium":
        if q._is_investment_budget(text, budget["snippets"]):
            score += 12
            reasons.append("Moderate investment/budget signal detected")
            has_substantive_signal = True
            print(f"-> MEDIUM SUBSTANTIVE BUDGET: score={score}, has_substantive_signal={has_substantive_signal}")
        else:
            score += 6
            reasons.append("Pricing/cost language detected")
            print(f"-> MEDIUM GENERIC BUDGET: score={score}")

    # Industry identification
    if category != "default":
        if q._is_substantive_industry_mention(text, category):
            score += 8
            reasons.append("Industry clearly relevant to business operations")
            has_substantive_signal = True
            print(f"-> SUBSTANTIVE INDUSTRY: score={score}, has_substantive_signal={has_substantive_signal}")
        else:
            score += 5
            reasons.append("Industry mentioned but not clearly central to operations")
            print(f"-> GENERIC INDUSTRY: score={score}")

    print(f"\n--- After main detection ---")
    print(f"score: {score}, has_substantive_signal: {has_substantive_signal}")
    print(f"reasons: {reasons}")
    
    # Require at least one substantive signal for qualification readiness
    if not has_substantive_signal:
        score = min(score, 20)
        reasons.append("Insufficient substantive evidence for qualification readiness")
        print(f"-> PENALTY APPLIED: score={score}")

    print(f"\n--- After substantive check ---")
    print(f"score: {score}, has_substantive_signal: {has_substantive_signal}")
    
    # Apply industry weight multipliers (only if we have substantive signals)
    if has_substantive_signal and multipliers:
        print(f"Applying multipliers...")
        for dimension, multiplier in multipliers.items():
            if multiplier > 1:
                substantive_score = score * 0.7
                bonus = round(substantive_score * (multiplier - 1) * 0.3)
                old_score = score
                score = min(100, score + bonus)
                print(f"  {dimension} ({multiplier}): {old_score} -> {score} (+{bonus})")

    print(f"\n--- After multipliers ---")
    print(f"score: {score}")

    # Extra signals from operator (if provided)
    if extra_signals:
        print(f"Processing extra signals: {extra_signals}")
        if extra_signals.get("recent_job_post"):
            score += 12
            reasons.append("Recent job posting observed (operator signal)")
            print(f"  -> recent_job_post: score={score}")
        if extra_signals.get("budget_mentioned"):
            score += 10
            reasons.append("Budget mentioned (operator signal)")
            print(f"  -> budget_mentioned: score={score}")
        if extra_signals.get("high_authority_domain"):
            score += 8
            reasons.append("High-authority domain observed (operator signal)")
            print(f"  -> high_authority_domain: score={score}")
        if extra_signals.get("multiple_touchpoints"):
            score += 12
            reasons.append("Multiple touchpoints observed (operator signal)")
            print(f"  -> multiple_touchpoints: score={score}")
        if extra_signals.get("positive_engagement"):
            score += 15
            reasons.append("Positive engagement observed (operator signal)")
            print(f"  -> positive_engagement: score={score}")

    score = min(100, max(0, score))
    print(f"\n--- Final score before tier: {score} ---")
    
    if score >= 80:
        tier = "HOT"
    elif score >= 55:
        tier = "WARM"
    elif score >= 30:
        tier = "QUALIFIED"
    else:
        tier = "COLD"
        
    print(f"Final tier: {tier}")
    print(f"Final reasons: {reasons}")
    
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
        "calculated_at": "DEBUG_TIMESTAMP",
        "basis": "Deterministic signal detection with corrections for qualification errors; not a calibrated conversion probability",
    }

# Test the problematic case
text = 'We provide construction services.'
industry = 'construction'
extra_signals = {'recent_job_post': True, 'budget_mentioned': True, 'positive_engagement': True}

result = debug_qualify_lead(text, industry, extra_signals)
print(f"\n=== FINAL RESULT ===")
print(f"Score: {result['qualification_score']}")
print(f"Tier: {result['tier']}")
