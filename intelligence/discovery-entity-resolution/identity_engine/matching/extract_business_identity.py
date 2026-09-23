# Extract public business identity from site
# Extract business name, etc., from HTML or structured data.

def extract_business_identity(html_content: str) -> dict:
    """Extract business identity from HTML content.
    Returns a dict with keys: name, legal_name, trading_names, website, phone, address.
    This is a placeholder implementation.
    """
    # In reality, we would parse HTML for schema.org, meta tags, visible text.
    # For now, return empty dict.
    return {
        "name": "",
        "legal_name": "",
        "trading_names": [],
        "website": "",
        "phone": "",
        "address": "",
    }