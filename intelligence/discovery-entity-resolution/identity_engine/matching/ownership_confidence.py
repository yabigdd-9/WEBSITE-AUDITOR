# Ownership confidence
# Compute confidence that a business owns a website based on various signals.

def compute_ownership_confidence(
    business_name: str,
    website: str,
    social_links: list,
    schema_org: dict,
    email_domain: str,
    phone: str,
    address: str,
) -> float:
    """Return a confidence score between 0 and 1 for website ownership.
    This is a simplified implementation that combines various signals.
    """
    score = 0.0
    # Signal 1: business name in website domain
    if business_name and website:
        import re
        domain = re.search(r'https?://([^/]+)', website)
        if domain:
            domain = domain.group(1).lower()
            name_token = business_name.lower().replace(' ', '')
            if name_token in domain:
                score += 0.2
    # Signal 2: email domain matches website domain
    if email_domain and website:
        email_domain = email_domain.lower()
        website_domain = re.search(r'https?://([^/]+)', website)
        if website_domain:
            website_domain = website_domain.group(1).lower()
            if email_domain == website_domain:
                score += 0.2
    # Signal 3: phone number found on website (simplified)
    if phone and website:
        # In reality, we would fetch the website and search for the phone.
        # Placeholder: assume phone is present if not empty.
        if phone:
            score += 0.2
    # Signal 4: address found on website (simplified)
    if address and website:
        if address:
            score += 0.2
    # Signal 5: schema.org LocalBusiness or Organization
    if schema_org and schema_org.get('@type') in ['LocalBusiness', 'Organization']:
        score += 0.2
    # Cap at 1.0
    return min(score, 1.0)