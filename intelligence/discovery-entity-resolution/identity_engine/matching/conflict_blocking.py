# Authoritative conflict blocking
# Block merge if authoritative IDs conflict.

def has_authoritative_conflict(record1_nzbn: str, record1_company_number: str,
                               record2_nzbn: str, record2_company_number: str) -> bool:
    """Return True if there is a conflict between authoritative IDs.
    Conflict if both records have NZBN and they differ, or both have company number and they differ.
    If only one record has an authoritative ID, not considered a conflict (maybe weak signal).
    """
    # NZBN conflict
    if record1_nzbn and record2_nzbn:
        if record1_nzbn.strip() != record2_nzbn.strip():
            return True
    # Company number conflict
    if record1_company_number and record2_company_number:
        if record1_company_number.strip() != record2_company_number.strip():
            return True
    return False