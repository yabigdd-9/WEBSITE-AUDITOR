# Address normalization interface
# Provides functions to normalize NZ addresses.

import re

def normalize_address(address: str) -> dict:
    """Normalize a NZ address into components.
    This is a simplified interface; a real implementation would use LINZ data or similar.
    Returns a dictionary with keys: street, suburb, city, region, postcode, latitude, longitude.
    For now, returns empty strings.
    """
    # Placeholder: in reality, we would parse the address and match against a dataset.
    return {
        "street": "",
        "suburb": "",
        "city": "",
        "region": "",
        "postcode": "",
        "latitude": None,
        "longitude": None,
    }

def normalize_suburb(suburb: str) -> str:
    """Normalize suburb/locality name."""
    if not suburb:
        return ""
    # Lowercase, remove extra whitespace, remove punctuation
    suburb = suburb.lower()
    suburb = re.sub(r'[^a-z0-9\s]', '', suburb)
    suburb = re.sub(r'\s+', ' ', suburb).strip()
    return suburb

def normalize_city(city: str) -> str:
    """Normalize city name."""
    return normalize_suburb(city)  # reuse same logic

def normalize_region(region: str) -> str:
    """Normalize region name."""
    if not region:
        return ""
    region = region.lower().strip()
    # Map common abbreviations and misspellings (simplified)
    region_map = {
        "auckland": "Auckland",
        "canterbury": "Canterbury",
        "wellington": "Wellington",
        "waikato": "Waikato",
        "bay of plenty": "Bay of Plenty",
        "otago": "Otago",
        "northland": "Northland",
        "taranaki": "Taranaki",
        "manawatu-wanganui": "Manawatū-Whanganui",
        "hawke's bay": "Hawke's Bay",
        "tisbury": "Tasman",
        "nelson": "Nelson",
        "marlborough": "Marlborough",
        "west coast": "West Coast",
        "southland": "Southland",
        "gore": "Gore",
        "invercargill": "Invercargill",
    }
    key = region
    if key in region_map:
        return region_map[key]
    # Title case as fallback
    return region.title()