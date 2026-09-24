"""
Exclusions engine for proposals.
"""

from typing import List, Dict, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class Exclusion:
    """Represents a single exclusion."""
    exclusion_id: str
    description: str
    scope_item_id: str  # Which scope item this exclusion relates to (optional)
    is_required: bool = True  # If false, exclusion may be omitted


class ExclusionsEngine:
    """Defines what work is outside the listed scope."""

    def __init__(self):
        # exclusions examples from plan
        self.exclusion_templates = [
            "work outside listed scope",
            "third-party subscription fees unless explicitly included",
            "content/legal review unless explicitly included",
            "guaranteed SEO rankings",
            "guaranteed revenue",
            "unlisted production infrastructure changes",
            "ongoing maintenance unless explicitly included",
            "training client staff unless explicitly included",
            "website hosting costs",
            "domain registration fees"
        ]

    def get_exclusions_for_scope(self, scope_type: str, scope_item_id: str = None) -> List[Exclusion]:
        """
        Get exclusions for a given scope type and scope item.
        Returns default exclusions.
        """
        # In a real implementation, this would be more sophisticated
        # and might have scope-specific exclusions

        exclusions = []
        for i, description in enumerate(self.exclusion_templates):
            exclusion = Exclusion(
                exclusion_id=f"excl_{i+1:02d}",
                description=description,
                scope_item_id=scope_item_id or "general",
                is_required=True
            )
            exclusions.append(exclusion)

        return exclusions

    def validate_exclusion(self, exclusion: Exclusion) -> bool:
        """
        Validate that an exclusion is well-formed.
        Must be specific, not hidden boilerplate.
        """
        if not exclusion.description or len(exclusion.description.strip()) == 0:
            logger.warning(f"Exclusion {exclusion.exclusion_id} has no description")
            return False

        # Check for boilerplate phrases that should be avoided
        boilerplate_phrases = [
            "acts of god",
            "force majeure",
            "unforeseen circumstances",
            "change in law"
        ]

        description_lower = exclusion.description.lower()
        for phrase in boilerplate_phrases:
            if phrase in description_lower:
                logger.warning(f"Exclusion {exclusion.exclusion_id} contains boilerplate phrase: {phrase}")
                return False

        return True

    def get_required_exclusions(self, exclusions: List[Exclusion]) -> List[Exclusion]:
        """Get only required exclusions."""
        return [e for e in exclusions if e.is_required]

    def get_optional_exclusions(self, exclusions: List[Exclusion]) -> List[Exclusion]:
        """Get only optional exclusions."""
        return [e for e in exclusions if not e.is_required]