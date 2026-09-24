"""
Canary mode implementation: limited scope allowed.
"""

from .resolver import get_feature_state

def is_canary_enabled(capability_id: str) -> bool:
    return get_feature_state(capability_id) == "CANARY"

def is_allowed_in_canary(entity_type: str, entity_id: str) -> bool:
    """
    Check if entity is allowed in canary mode.
    For simplicity, we allow synthetic fixtures and approved bounded entities.
    In practice, this would check against a list of approved entities.
    """
    # Placeholder: allow if entity_id contains "synthetic" or is in a predefined list
    if "synthetic" in entity_id.lower():
        return True
    # Example approved bounded entities list (could be loaded from config)
    approved_entities = {
        "business": ["synthetic-business-1", "synthetic-business-2"],
        "website": ["synthetic-website-1"]
    }
    return entity_id in approved_entities.get(entity_type, [])