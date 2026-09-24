"""
Assumptions engine for proposals.
"""

from typing import List, Dict, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class Assumption:
    """Represents a single assumption."""
    assumption_id: str
    description: str
    scope_item_id: str  # Which scope item this assumption relates to (optional)
    is_critical: bool = False  # If false, proposal may still proceed


class AssumptionsEngine:
    """Documents assumptions visible in the proposal."""

    def __init__(self):
        # assumptions examples from plan
        self.assumption_templates = [
            "existing hosting remains available",
            "required credentials supplied by client",
            "scope limited to listed URLs",
            "third-party service remains functional",
            "client provides timely feedback",
            "no unexpected technical complications arise",
            "client approves design concepts in timely manner",
            "current CMS/theme supports required changes"
        ]

    def get_assumptions_for_scope(self, scope_type: str, scope_item_id: str = None) -> List[Assumption]:
        """
        Get assumptions for a given scope type and scope item.
        Returns default assumptions if none specified.
        """
        # In a real implementation, this would be more sophisticated
        # and might have scope-specific assumptions

        assumptions = []
        for i, description in enumerate(self.assumption_templates):
            assumption = Assumption(
                assumption_id=f"assump_{i+1:02d}",
                description=description,
                scope_item_id=scope_item_id or "general",
                is_critical=(i < 3)  # First few are more critical
            )
            assumptions.append(assumption)

        return assumptions

    def validate_assumption(self, assumption: Assumption) -> bool:
        """
        Validate that an assumption is well-formed.
        """
        if not assumption.description or len(assumption.description.strip()) == 0:
            logger.warning(f"Assumption {assumption.assumption_id} has no description")
            return False

        return True

    def get_critical_assumptions(self, assumptions: List[Assumption]) -> List[Assumption]:
        """Get only critical assumptions."""
        return [a for a in assumptions if a.is_critical]

    def get_non_critical_assumptions(self, assumptions: List[Assumption]) -> List[Assumption]:
        """Get only non-critical assumptions."""
        return [a for a in assumptions if not a.is_critical]