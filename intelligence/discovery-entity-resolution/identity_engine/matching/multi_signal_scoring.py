# Multi-signal evidence scoring
# Combine signals from various matches to compute a confidence score.

def compute_confidence_score(signals: dict) -> float:
    """Compute a confidence score based on matched signals.
    Signals is a dict with keys like 'nzbn_match', 'company_number_match',
    'name_domain_match', 'name_phone_match', 'name_location_match',
    each being a boolean or a weight.
    Returns a score between 0 and 1.
    This is a simplified implementation.
    """
    # Define weights for each signal (example)
    weights = {
        'nzbn_match': 0.4,
        'company_number_match': 0.4,
        'name_domain_match': 0.2,
        'name_phone_match': 0.2,
        'name_location_match': 0.2,
    }
    score = 0.0
    total_weight = 0.0
    for signal, present in signals.items():
        if present:
            score += weights.get(signal, 0.0)
        total_weight += weights.get(signal, 0.0)
    if total_weight == 0:
        return 0.0
    # Normalize by total weight (so max score is 1 if all signals present)
    return min(score / total_weight, 1.0)