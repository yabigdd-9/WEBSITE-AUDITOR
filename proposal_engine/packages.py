"""
Package intelligence for the WEBSITE-AUDITOR proposal engine.
"""

from typing import List, Dict, Any
from .schema import ScopeItem


def recommend_package(scope_items: List[ScopeItem]) -> str:
    """
    Recommend a package based on the scope items.
    This is a placeholder implementation.
    Returns a package ID (e.g., 'focused_fix', 'technical_upgrade', etc.)
    """
    # For now, we'll just return the first package if there's only one scope item and it's small.
    # In reality, we would check the scope items against package definitions in config/pricing/packages.yaml
    if len(scope_items) == 1 and scope_items[0].effort_band in ["XS", "S"]:
        return "focused_fix"
    elif len(scope_items) > 1:
        # Check if all scope items are technical in nature (placeholder)
        return "technical_upgrade"
    else:
        return "focused_fix"  # default


def get_package_details(package_id: str) -> Dict[str, Any]:
    """
    Load package details from config/pricing/packages.yaml.
    For now, we'll return a mock.
    """
    # In a real implementation, we would load the YAML file.
    # We'll return a placeholder.
    return {
        "package_id": package_id,
        "name": "Unknown Package",
        "description": "",
        "included_scope": [],
        "excluded_scope": [],
        "effort_band": "XS",
        "estimate_band": "XS-S",
    }
