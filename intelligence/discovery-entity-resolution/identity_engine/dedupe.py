# Operational candidate dedupe
# Remove duplicate candidates based on key fields.

def deduplicate_candidates(candidates, key_func=None):
    """Remove duplicate candidates from a list.
    Args:
        candidates: list of dicts representing candidates.
        key_func: function that returns a key for a candidate.
                  If None, use the entire dict as key (not recommended for dicts).
    Returns:
        list of candidates with duplicates removed (keeping first occurrence).
    """
    seen = set()
    deduped = []
    for candidate in candidates:
        if key_func:
            key = key_func(candidate)
        else:
            # Convert dict to a tuple of sorted items for hashing
            key = tuple(sorted(candidate.items()))
        if key not in seen:
            seen.add(key)
            deduped.append(candidate)
    return deduped

# Example key functions:
def key_by_nzbn(candidate):
    return candidate.get('nzbn')

def key_by_website(candidate):
    return candidate.get('website')