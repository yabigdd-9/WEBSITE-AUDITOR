"""
Approval engine for proposals including human review packet, hashing, and versioning.
"""

import hashlib
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Import our schema to work with Proposal objects
from .schema import Proposal, ProposalStatus, ProposalVersionState


@dataclass
class HumanReviewPacket:
    """Packet of information for human review of a proposal."""
    proposal: Proposal
    scope_summary: str
    evidence_summary: List[str]
    calculation_details: Dict[str, Any]
    risk_assessment: Dict[str, Any]
    decisions: List[str]  # approve, revise, reject
    review_id: str = field(default_factory=lambda: f"review_{int(datetime.now().timestamp())}")
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ApprovalInfo:
    """Information about proposal approval."""
    approval_id: str
    proposal_id: str
    proposal_version: str
    approved_by: str
    approved_at: datetime
    approval_hash: str
    scope_hash: str
    pricing_hash: str


class ApprovalEngine:
    """Handles proposal approval, hashing, and versioning."""

    def __init__(self):
        pass

    def build_human_review_packet(self, proposal: Proposal,
                                scope_items: List[Any] = None,
                                evidence_refs: List[str] = None,
                                pricing_calculation: Dict[str, Any] = None,
                                assumptions: List[str] = None,
                                exclusions: List[str] = None) -> HumanReviewPacket:
        """
        Build a human review packet for a proposal.
        Includes commercial, evidence, calculation, risks, and controls.
        """
        # Commercial: proposal draft, quote range, scope
        scope_summary = self._create_scope_summary(scope_items or [])

        # Evidence: findings, proof, screenshots
        evidence_summary = evidence_refs or []

        # Calculation: effort breakdown, price calculation
        calculation_details = pricing_calculation or {}

        # Risks: assumptions, unknowns, exclusions
        risk_assessment = {
            'assumptions': assumptions or [],
            'exclusions': exclusions or [],
            'unknowns': []  # To be filled by integration
        }

        # Controls: approve, revise, reject
        decisions = ["approve", "revise", "reject"]

        return HumanReviewPacket(
            proposal=proposal,
            scope_summary=scope_summary,
            evidence_summary=evidence_summary,
            calculation_details=calculation_details,
            risk_assessment=risk_assessment,
            decisions=decisions
        )

    def _create_scope_summary(self, scope_items: List[Any]) -> str:
        """Create a summary of scope items for the review packet."""
        if not scope_items:
            return "No scope items defined"

        summary_parts = [f"{len(scope_items)} scope item(s):"]
        for item in scope_items[:5]:  # Limit to first 5
            if hasattr(item, 'title'):
                summary_parts.append(f"- {item.title}")
            elif isinstance(item, dict) and 'title' in item:
                summary_parts.append(f"- {item['title']}")
            else:
                summary_parts.append(f"- {str(item)[:50]}")

        if len(scope_items) > 5:
            summary_parts.append(f"... and {len(scope_items) - 5} more")

        return "\n".join(summary_parts)

    def generate_approval_hash(self, proposal: Proposal,
                             scope_items: List[Any] = None,
                             pricing_data: Dict[str, Any] = None) -> str:
        """
        Generate a hash for approval integrity.
        Includes proposal body, scope, pricing, proposal version, and pricing version.
        """
        # Create a string representation of the data to hash
        hash_data = {
            'proposal_body': self._proposal_to_dict(proposal),
            'scope': [self._scope_item_to_dict(item) for item in (scope_items or [])],
            'pricing': pricing_data or {},
            'proposal_version': proposal.proposal_version,
            'pricing_version': getattr(proposal, 'pricing_version', 'unknown')
        }

        # Convert to JSON string for consistent hashing
        hash_string = json.dumps(hash_data, sort_keys=True, default=str)

        # Generate SHA256 hash
        return hashlib.sha256(hash_string.encode()).hexdigest()

    def _proposal_to_dict(self, proposal: Proposal) -> Dict[str, Any]:
        """Convert Proposal object to dictionary for hashing."""
        return {
            'proposal_id': proposal.proposal_id,
            'business_id': proposal.business_id,
            'website_id': proposal.website_id,
            'opportunity_id': proposal.opportunity_id,
            'proof_id': proposal.proof_id,
            'proposal_version': proposal.proposal_version,
            'pricing_version': getattr(proposal, 'pricing_version', 'unknown'),
            'currency': proposal.currency,
            'status': proposal.status.value if hasattr(proposal.status, 'value') else str(proposal.status),
            'scope_items_count': len(proposal.scope_items),
            'deliverables_count': len(proposal.deliverables),
            'effort': proposal.effort,
            'estimate_band': proposal.estimate_band
        }

    def _scope_item_to_dict(self, scope_item: Any) -> Dict[str, Any]:
        """Convert scope item to dictionary for hashing."""
        if hasattr(scope_item, '__dict__'):
            return {
                'scope_id': getattr(scope_item, 'scope_id', 'unknown'),
                'title': getattr(scope_item, 'title', 'unknown'),
                'problem': getattr(scope_item, 'problem', 'unknown'),
                'affected_urls': getattr(scope_item, 'affected_urls', []),
                'effort_band': getattr(scope_item, 'effort_band', 'unknown'),
                'finding_ids': getattr(scope_item, 'finding_ids', [])
            }
        elif isinstance(scope_item, dict):
            return {
                'scope_id': scope_item.get('scope_id', 'unknown'),
                'title': scope_item.get('title', 'unknown'),
                'problem': scope_item.get('problem', 'unknown'),
                'affected_urls': scope_item.get('affected_urls', []),
                'effort_band': scope_item.get('effort_band', 'unknown'),
                'finding_ids': scope_item.get('finding_ids', [])
            }
        else:
            return {'description': str(scope_item)[:100]}

    def validate_approval(self, proposal: Proposal, approval_info: ApprovalInfo) -> bool:
        """
        Validate that an approval is still valid for the current proposal.
        Invalidates approval after edits to proposal, scope, or pricing.
        """
        # Re-generate the hash based on current proposal state
        current_hash = self.generate_approval_hash(
            proposal,
            scope_items=getattr(proposal, 'scope_items', []),
            pricing_data={}  # Would be passed in real implementation
        )

        # Check if hashes match
        if current_hash != approval_info.approval_hash:
            logger.warning(f"Approval invalidated: proposal has changed since approval")
            return False

        # Check if proposal version matches
        if proposal.proposal_version != approval_info.proposal_version:
            logger.warning(f"Approval invalidated: proposal version mismatch")
            return False

        return True

    def create_approval_info(self, proposal: Proposal, approved_by: str,
                           scope_items: List[Any] = None,
                           pricing_data: Dict[str, Any] = None) -> ApprovalInfo:
        """Create approval information for a proposal."""
        approval_hash = self.generate_approval_hash(proposal, scope_items, pricing_data)

        return ApprovalInfo(
            approval_id=f"approval_{int(datetime.now().timestamp())}",
            proposal_id=proposal.proposal_id,
            proposal_version=proposal.proposal_version,
            approved_by=approved_by,
            approved_at=datetime.now(),
            approval_hash=approval_hash,
            scope_hash="",  # Would be calculated from scope items
            pricing_hash=""  # Would be calculated from pricing data
        )

    def get_approval_status(self, proposal: Proposal,
                          approval_info: Optional[ApprovalInfo] = None) -> str:
        """
        Get the approval status of a proposal.
        """
        if not approval_info:
            return "NOT_APPROVED"

        if self.validate_approval(proposal, approval_info):
            return "APPROVED"
        else:
            return "APPROVAL_INVALIDATED"