# Parent/branch model
# Determine if two records represent a parent and branch.

def is_parent_branch(record1_nzbn: str, record1_locations: list,
                     record2_nzbn: str, record2_locations: list) -> bool:
    """Return True if records share same NZBN but have different locations.
    This is a simplified parent/branch detection.
    """
    if not record1_nzbn or not record2_nzbn:
        return False
    if record1_nzbn.strip() != record2_nzbn.strip():
        return False
    # If both have locations and they are different, consider parent/branch
    # For simplicity, we just check if location lists are not identical.
    # In reality, we would compare addresses.
    if record1_locations and record2_locations:
        # Simple check: if the sets of locations are different
        set1 = set(record1_locations)
        set2 = set(record2_locations)
        if set1 != set2:
            return True
    return False