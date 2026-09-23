# Service-area business support
# Identify and support service-area businesses (those that serve an area but lack a street address).

def is_service_area_business(address: str, service_area_indicators: list) -> bool:
    """Return True if the business is a service-area business.
    Simple heuristic: if address is empty or lacks street number but has region/service area indicators.
    """
    if not address or address.strip() == "":
        # No address at all, could be service-area
        return bool(service_area_indicators)
    # Could check if address lacks a street number but has a region name.
    # For simplicity, we'll just return True if there are service area indicators and no street number.
    import re
    # Check if address contains a digit (likely a street number)
    if re.search(r'\d', address):
        return False  # Likely has a street number
    # If no digit but has service area indicators, consider service-area
    return bool(service_area_indicators)