"""
Acceptance criteria engine for proposals.
"""

from typing import List, Dict, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class AcceptanceCriterion:
    """Represents a single acceptance criterion."""
    criterion_id: str
    description: str
    scope_item_id: str  # Which scope item this criterion belongs to
    verification_method: str  # How to verify this criterion
    is_required: bool = True


class AcceptanceCriteriaEngine:
    """Defines what completion means before a proposal is approved."""

    def __init__(self):
        # acceptance_criteria examples from plan
        self.criteria_templates = {
            'broken_link': [
                "target links return expected successful response",
                "no broken links found in verified pages"
            ],
            'cta': [
                "CTA visible at required breakpoints",
                "destination reachable and functional",
                "CTA styling consistent with brand guidelines"
            ],
            'schema': [
                "JSON-LD parses without errors",
                "required configured checks pass",
                "schema.org validation successful"
            ],
            'performance': [
                "specified local optimization implemented",
                "no severe regression in performance benchmarks",
                "core web vitals meet defined thresholds"
            ],
            'mobile': [
                "no target overflow at tested viewport",
                "touch targets meet minimum size requirements",
                "responsive layout functions correctly"
            ],
            'security': [
                "security headers present and correctly configured",
                "no vulnerable JavaScript libraries detected",
                "SSL certificate valid and properly installed"
            ],
            'local_seo': [
                "LocalBusiness schema present and valid",
                "NAP consistency verified across directories",
                "Google My Business profile claimed and optimized"
            ]
        }

    def get_criteria_for_scope(self, scope_type: str, scope_item_id: str) -> List[AcceptanceCriterion]:
        """
        Get acceptance criteria for a given scope type and scope item.
        Returns default criteria if scope type not found.
        """
        criteria_list = self.criteria_templates.get(scope_type.lower())

        if not criteria_list:
            logger.warning(f"No acceptance criteria found for scope type: {scope_type}")
            # Default criteria
            criteria_list = [
                "implementation completed as specified",
                "verification of work completion",
                "no negative impact on existing functionality"
            ]

        criteria = []
        for i, description in enumerate(criteria_list):
            criterion = AcceptanceCriterion(
                criterion_id=f"ac_{scope_item_id}_{i+1:02d}",
                description=description,
                scope_item_id=scope_item_id,
                verification_method="manual verification"  # Default, could be enhanced
            )
            criteria.append(criterion)

        return criteria

    def validate_criterion(self, criterion: AcceptanceCriterion) -> bool:
        """
        Validate that an acceptance criterion is well-formed.
        """
        if not criterion.description or len(criterion.description.strip()) == 0:
            logger.warning(f"Acceptance criterion {criterion.criterion_id} has no description")
            return False

        if not criterion.scope_item_id or len(criterion.scope_item_id.strip()) == 0:
            logger.warning(f"Acceptance criterion {criterion.criterion_id} has no scope item ID")
            return False

        return True

    def get_criteria_description(self, scope_type: str) -> str:
        """Get general description of acceptance criteria for a scope type."""
        descriptions = {
            'broken_link': "Ensure all links are functional and point to correct destinations",
            'cta': "Verify calls-to-action are visible, functional, and convert effectively",
            'schema': "Confirm structured data is correctly implemented and valid",
            'performance': "Validate performance improvements meet specified benchmarks",
            'mobile': "Ensure mobile responsiveness and usability standards are met",
            'security': "Confirm security measures are properly implemented and effective",
            'local_seo': "Verify local search optimization is complete and accurate"
        }
        return descriptions.get(scope_type.lower(), f"Verify {scope_type} work is completed satisfactorily")