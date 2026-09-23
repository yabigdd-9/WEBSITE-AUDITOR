# Name + location matching
# Match if normalized names match and locations are the same (using normalized suburb/city/region).

from .normalization.business_name_normalization import normalize_name
from .normalization.address_normalization import normalize_suburb, normalize_city, normalize_region

def match_by_name_and_location(record1_name: str, record1_suburb: str, record1_city: str, record1_region: str,
                               record2_name: str, record2_suburb: str, record2_city: str, record2_region: str) -> bool:
    """Return True if names match and location matches (suburb, city, region)."""
    name1 = normalize_name(record1_name)
    name2 = normalize_name(record2_name)
    if not name1 or not name2 or name1 != name2:
        return False
    # Compare location components
    if normalize_suburb(record1_suburb) != normalize_suburb(record2_suburb):
        return False
    if normalize_city(record1_city) != normalize_city(record2_city):
        return False
    if normalize_region(record1_region) != normalize_region(record2_region):
        return False
    return True