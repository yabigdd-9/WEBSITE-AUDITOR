# Name + phone matching
# Match if normalized names match and phones match (normalized).

from .normalization.business_name_normalization import normalize_name
from .normalization.phone_normalization import normalize_nz_phone

def match_by_name_and_phone(record1_name: str, record1_phone: str,
                            record2_name: str, record2_phone: str) -> bool:
    """Return True if names match and phones match."""
    name1 = normalize_name(record1_name)
    name2 = normalize_name(record2_name)
    if not name1 or not name2 or name1 != name2:
        return False
    phone1 = normalize_nz_phone(record1_phone)
    phone2 = normalize_nz_phone(record2_phone)
    if not phone1 or not phone2:
        return False
    return phone1 == phone2