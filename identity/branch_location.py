"""
Branch/location awareness for identity.
"""

def is_branch_location(parent_id: str, child_id: str, relationship: str) -> bool:
    """
    Determine if child is a branch/location of parent.
    For simplicity, we assume relationship indicates branch/location.
    """
    return relationship in ('branch', 'location', 'subsidiary')

def separate_branch_location(parent_id: str, child_id: str) -> bool:
    """
    Policy: parent_child_separate: true -> branches and locations are separate entities.
    """
    return True  # always treat as separate