"""
Template selection for the WEBSITE-AUDITOR proposal engine.
"""

from typing import List
from .schema import ScopeItem


def select_template(scope_items: List[ScopeItem], package_id: Optional[str] = None) -> str:
    """
    Select a template name based on the scope items or package ID.
    Returns the template name (without extension) to be used with the reporting module.
    """
    if package_id:
        # Map package_id to template name
        package_to_template = {
            "focused_fix": "quick_fix",
            "technical_upgrade": "technical_upgrade",
            "conversion_upgrade": "conversion_upgrade",
            "modernization": "modernization",
        }
        return package_to_template.get(package_id, "quick_fix")

    # If no package_id, infer from scope items
    # For simplicity, we'll count the scope items and check effort bands
    if len(scope_items) == 1:
        # Single scope item -> quick fix
        return "quick_fix"
    elif len(scope_items) > 1:
        # Multiple scope items -> check if they are all technical (placeholder)
        # We'll just return technical_upgrade for now
        return "technical_upgrade"
    else:
        # No scope items -> default to quick fix
        return "quick_fix"


def get_template_path(template_name: str) -> str:
    """
    Get the file path for a given template name.
    Assumes templates are in the templates/proposals/ directory.
    """
    return f"templates/proposals/{template_name}.md"
