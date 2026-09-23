# Category normalization
# Normalize business categories/industries for comparison.

def normalize_category(category: str) -> str:
    """Normalize a category string.
    Steps:
      - Lowercase
      - Remove punctuation
      - Remove extra whitespace
    Returns normalized string.
    """
    if not category:
        return ""
    import re
    category = category.lower()
    category = re.sub(r'[^a-z0-9\s]', '', category)
    category = re.sub(r'\s+', ' ', category).strip()
    return category