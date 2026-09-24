"""
Deliverables mapping engine for proposal scope items.
"""

from typing import List, Dict, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class DeliverableMapping:
    """Mapping of scope item to deliverables."""
    scope_type: str
    deliverables: List[str]
    description: str


class DeliverablesEngine:
    """Maps scope items to concrete deliverables."""

    def __init__(self):
        # deliverables_mapping from plan
        self.deliverables_mappings = {
            'website_health': DeliverableMapping(
                scope_type='website_health',
                deliverables=[
                    "updated title/meta recommendations",
                    "implementation",
                    "verification"
                ],
                description="Technical hygiene and website health improvements"
            ),
            'performance': DeliverableMapping(
                scope_type='performance',
                deliverables=[
                    "optimized assets",
                    "resource changes",
                    "before/after lab evidence"
                ],
                description="Performance optimization and resource improvements"
            ),
            'conversion': DeliverableMapping(
                scope_type='conversion',
                deliverables=[
                    "CTA/form improvements",
                    "responsive verification",
                    "flow verification"
                ],
                description="Conversion rate optimization improvements"
            ),
            'local_visibility': DeliverableMapping(
                scope_type='local_visibility',
                deliverables=[
                    "LocalBusiness schema implementation",
                    "location-page cleanup evidence",
                    "local consistency verification"
                ],
                description="Local search visibility improvements"
            ),
            'modernization': DeliverableMapping(
                scope_type='modernization',
                deliverables=[
                    "approved UI changes",
                    "responsive testing",
                    "technical regression check"
                ],
                description="Site modernization and technology updates"
            ),
            'security_hygiene': DeliverableMapping(
                scope_type='security_hygiene',
                deliverables=[
                    "security header implementation",
                    "vulnerable JS remediation",
                    "security verification report"
                ],
                description="Security hygiene improvements"
            )
        }

    def get_deliverables_for_scope(self, scope_type: str) -> List[str]:
        """
        Get deliverables for a given scope type.
        Returns default deliverables if scope type not found.
        """
        mapping = self.deliverables_mappings.get(scope_type.lower())
        if mapping:
            return mapping.deliverables.copy()

        # Default deliverables for unknown scope types
        logger.warning(f"No deliverables mapping found for scope type: {scope_type}")
        return [
            "implementation",
            "verification",
            "documentation"
        ]

    def get_deliverable_description(self, scope_type: str) -> str:
        """Get description for a scope type."""
        mapping = self.deliverables_mappings.get(scope_type.lower())
        if mapping:
            return mapping.description
        return f"Work related to {scope_type}"

    def enhance_scope_item_with_deliverables(self, scope_item) -> object:
        """
        Enhance a scope item with appropriate deliverables based on its type.
        This would be called after scope item creation.
        """
        # Try to determine scope type from scope item title or other attributes
        scope_type = self._infer_scope_type(scope_item)

        # Get deliverables for this scope type
        deliverables = self.get_deliverables_for_scope(scope_type)

        # Update scope item deliverables if they're generic
        if hasattr(scope_item, 'deliverables') and scope_item.deliverables:
            # Check if deliverables are generic (like just "implementation")
            generic_deliverables = {"implementation", "verification", "documentation"}
            if all(d.lower() in generic_deliverables for d in scope_item.deliverables):
                scope_item.deliverables = deliverables
        elif hasattr(scope_item, 'deliverables'):
            scope_item.deliverables = deliverables

        return scope_item

    def _infer_scope_type(self, scope_item) -> str:
        """
        Infer scope type from scope item attributes.
        In a real implementation, this would be more sophisticated.
        """
        # Check if scope_item has a scope_type attribute
        if hasattr(scope_item, 'scope_type') and scope_item.scope_type:
            return scope_item.scope_type

        # Infer from title or problem description
        title_lower = getattr(scope_item, 'title', '').lower()
        problem_lower = getattr(scope_item, 'problem', '').lower()

        # Simple keyword matching
        if any(keyword in title_lower or keyword in problem_lower
               for keyword in ['broken', 'link', 'redirect', 'indexability', 'hygiene', 'ssl']):
            return 'website_health'
        elif any(keyword in title_lower or keyword in problem_lower
                 for keyword in ['performance', 'speed', 'optimization', 'loading', 'page speed']):
            return 'performance'
        elif any(keyword in title_lower or keyword in problem_lower
                 for keyword in ['cta', 'form', 'conversion', 'booking', 'trust']):
            return 'conversion'
        elif any(keyword in title_lower or keyword in problem_lower
                 for keyword in ['local', 'schema', 'nap', 'google my business', 'citation']):
            return 'local_visibility'
        elif any(keyword in title_lower or keyword in problem_lower
                 for keyword in ['modern', 'update', 'component', 'page builder', 'responsive']):
            return 'modernization'
        elif any(keyword in title_lower or keyword in problem_lower
                 for keyword in ['security', 'header', 'vulnerable', 'malware', 'scan']):
            return 'security_hygiene'
        else:
            # Default to website_health
            return 'website_health'