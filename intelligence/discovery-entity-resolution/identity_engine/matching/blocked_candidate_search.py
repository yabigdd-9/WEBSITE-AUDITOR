# Blocked candidate search
# Check if a candidate should be blocked from consideration (e.g., due to conflicts).

def is_blocked(record1_id: str, record2_id: str, block_list: set) -> bool:
    """Return True if the pair (record1_id, record2_id) is in the block list.
    block_list is a set of tuples (id1, id2) with ids sorted.
    """
    # Ensure consistent ordering
    ids = tuple(sorted([record1_id, record2_id]))
    return ids in block_list