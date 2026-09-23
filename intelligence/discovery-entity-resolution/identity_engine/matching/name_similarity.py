# Name similarity
# Compute similarity between two names.

def name_similarity(name1: str, name2: str) -> float:
    """Return a similarity score between 0 and 1 for two names.
    This is a placeholder implementation using simple token overlap.
    """
    if not name1 or not name2:
        return 0.0
    # Tokenize by whitespace
    tokens1 = set(name1.lower().split())
    tokens2 = set(name2.lower().split())
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    return len(intersection) / len(union)