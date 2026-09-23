# Business name normalization
# Normalize legal and trading names for comparison.

import re

def normalize_name(name: str) -> str:
    """Normalize a business name for comparison.
    Steps:
      - Lowercase
      - Remove punctuation
      - Remove extra whitespace
      - Remove common legal suffixes (optional, kept separately)
    Returns normalized string.
    """
    if not name:
        return ""
    # Lowercase
    name = name.lower()
    # Remove punctuation (keep letters, digits, spaces)
    name = re.sub(r'[^a-z0-9\s]', '', name)
    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def extract_legal_suffix_removed_name(name: str) -> str:
    """Remove common legal suffixes to get core name.
    Returns name with suffix removed, and the suffix separately.
    For simplicity, we just return the name after removing known suffixes.
    """
    if not name:
        return "", ""
    # List of common legal suffixes in NZ (case-insensitive)
    suffixes = [
        'limited', 'ltd', 'tapui a limited', 'tapui a lt',
        'incorporated', 'inc',
        'proprietary', 'pty',
        'unlimited', 'ultd',
        'no liability', 'nol',
    ]
    # We'll try to remove from the end
    normalized = name.lower()
    for suffix in suffixes:
        if normalized.endswith(' ' + suffix):
            # Remove the suffix
            core = name[:-(len(suffix)+1)].strip()
            return core, suffix
        elif normalized == suffix:
            return "", suffix
    # No suffix found
    return name, ""