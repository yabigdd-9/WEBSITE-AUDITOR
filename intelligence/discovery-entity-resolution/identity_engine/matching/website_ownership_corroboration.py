# Website ownership corroboration
# Corroborate website ownership with other signals.

def corroborate_website_ownership(business_name: str, website: str,
                                  social_links: list, schema_org: dict) -> float:
    """Return a confidence score for website ownership based on corroboration.
    This is a placeholder implementation.
    """
    score = 0.0
    # Check if business name appears in website domain (simple)
    if business_name and website:
        # Extract domain from website (simplified)
        import re
        domain = re.search(r'https?://([^/]+)', website)
        if domain:
            domain = domain.group(1).lower()
            # Check if business name (lowercase, no spaces) is in domain
            name_token = business_name.lower().replace(' ', '')
            if name_token in domain:
                score += 0.3
    # Check social links
    if social_links:
        score += 0.2 * min(len(social_links), 3) / 3  # up to 0.2
    # Check schema.org
    if schema_org and schema_org.get('@type') in ['LocalBusiness', 'Organization']:
        score += 0.3
    return min(score, 1.0)