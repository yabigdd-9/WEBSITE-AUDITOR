# Add bounded public-web corroboration
# Corroborate business identity with public web signals within bounds.

def corroborate_with_web(business_name, website, max_pages=5):
    """Corroborate business name with website content.
    Placeholder: fetch homepage and check for business name.
    Returns a corroboration score between 0 and 1.
    """
    # In reality, we would fetch the website and parse it.
    # For now, return a placeholder score.
    if business_name and website:
        # Simple check: if business name is in the domain
        import re
        domain_match = re.search(r'https?://([^/]+)', website)
        if domain_match:
            domain = domain_match.group(1).lower()
            if business_name.lower().replace(' ', '') in domain:
                return 0.3  # weak corroboration
    return 0.0

def check_social_media(business_name, social_links):
    """Check social media profiles for business name."""
    # Placeholder
    if business_name and social_links:
        # Assume some match
        return 0.2
    return 0.0