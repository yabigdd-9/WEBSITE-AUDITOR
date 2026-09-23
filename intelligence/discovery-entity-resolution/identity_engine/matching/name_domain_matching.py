# Name + domain matching
# Match if normalized names match and domains match (or are subdomains of same registrable domain).

from .normalization.business_name_normalization import normalize_name
from .normalization.domain_normalization import get_registrable_domain

def match_by_name_and_domain(record1_name: str, record1_hostname: str,
                             record2_name: str, record2_hostname: str) -> bool:
    """Return True if names match and domains are under same registrable domain."""
    # Normalize names
    name1 = normalize_name(record1_name)
    name2 = normalize_name(record2_name)
    if not name1 or not name2 or name1 != name2:
        return False
    # Get registrable domains
    reg1 = get_registrable_domain(record1_hostname)
    reg2 = get_registrable_domain(record2_hostname)
    if not reg1 or not reg2:
        return False
    return reg1 == reg2