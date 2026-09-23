# NZBN exact linking
# Link records by exact NZBN match.

def link_by_nzbn(record1_nzbn: str, record2_nzbn: str) -> bool:
    """Return True if two records have the same NZBN and both are non-empty.
    Args:
        record1_nzbn: NZBN of record 1 (string)
        record2_nzbn: NZBN of record 2 (string)
    Returns:
        Boolean indicating if they match by NZBN.
    """
    if not record1_nzbn or not record2_nzbn:
        return False
    return record1_nzbn.strip() == record2_nzbn.strip()