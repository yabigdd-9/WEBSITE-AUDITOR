# Fuzzy auto-merge prevention
# Ensure that fuzzy candidates (low confidence) are not automatically merged.

def should_auto_merge(confidence: float, threshold: float = 0.85) -> bool:
    """Return True if confidence is above threshold for auto-merge.
    Fuzzy candidates typically have confidence below threshold, so this returns False.
    """
    return confidence >= threshold