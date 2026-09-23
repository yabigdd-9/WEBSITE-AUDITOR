# Category similarity
# Compute similarity between two categories.

def category_similarity(cat1: str, cat2: str) -> float:
    """Return similarity between 0 and 1 for two categories.
    Simple token overlap similarity.
    """
    if not cat1 or not cat2:
        return 0.0
    # Tokenize by whitespace and punctuation
    import re
    tokens1 = set(re.findall(r'\w+', cat1.lower()))
    tokens2 = set(re.findall(r'\w+', cat2.lower()))
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    return len(intersection) / len(union)