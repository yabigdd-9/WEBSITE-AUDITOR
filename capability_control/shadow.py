"""
Shadow mode implementation: prevents canonical state mutations.
"""

from .resolver import get_feature_state

def is_shadow_enabled(capability_id: str) -> bool:
    return get_feature_state(capability_id) == "SHADOW"

def allow_state_mutation(capability_id: str) -> bool:
    """Return True if state mutation is allowed for this capability."""
    if is_shadow_enabled(capability_id):
        return False
    # In canary mode, mutations may be allowed for bounded entities
    # For simplicity, we allow unless shadow
    return True