"""
Approval module for the WEBSITE-AUDITOR proposal engine.
"""

import hashlib
import json
from typing import Dict, Any, Optional
from .schema import Proposal


def generate_approval_hash(proposal: Proposal) -> str:
    """
    Generate a hash for approval purposes based on proposal body, scope, pricing,
    proposal version, and pricing version.
    """
    # We'll create a dictionary of the fields to include in the hash
    hash_data = {
        "proposal_id": proposal.proposal_id,
        "business_id": proposal.business_id,
        "website_id": proposal.website_id,
        "opportunity_id": proposal.opportunity_id,
        "proof_id": proposal.proof_id,
        "proposal_version": proposal.proposal_version,
        "pricing_version": proposal.pricing_version,
        "currency": proposal.currency,
        # Scope items: we need to serialize them in a deterministic way
        "scope_items": [
            {
                "scope_id": item.scope_id,
                "title": item.title,
                "problem": item.problem,
                "evidence": item.evidence,
                "affected_urls": sorted(item.affected_urls),  # sort for determinism
                "root_cause": item.root_cause,
                "proposed_work": item.proposed_work,
                "deliverables": sorted(item.deliverables),
                "verification": item.verification,
                "effort_band": item.effort_band,
                "dependencies": sorted(item.dependencies),
                "risk": item.risk,
                "finding_ids": sorted(item.finding_ids),
            }
            for item in proposal.scope_items
        ],
        "deliverables": sorted(proposal.deliverables),
        "effort": proposal.effort,
        "estimate_band": proposal.estimate_band,
        "assumptions": sorted(proposal.assumptions),
        "exclusions": sorted(proposal.exclusions),
        "acceptance_criteria": sorted(proposal.acceptance_criteria),
        "optional_addons": sorted(proposal.optional_addons),
        "evidence_refs": sorted(proposal.evidence_refs),
        "limitations": sorted(proposal.limitations),
    }

    # Convert to JSON string with sorted keys for determinism
    json_str = json.dumps(hash_data, sort_keys=True)
    # Generate SHA256 hash
    return hashlib.sha256(json_str.encode('utf-8')).hexdigest()


def create_human_review_packet(proposal: Proposal, calculation_components: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Create a human review packet that includes the proposal, evidence, calculation, risks, and controls.
    """
    packet = {
        "proposal": proposal,
        "approval_hash": generate_approval_hash(proposal),
        "calculation": calculation_components or {},
        "risks": {
            "assumptions": proposal.assumptions,
            "exclusions": proposal.exclusions,
            "limitations": proposal.limitations,
        },
        "controls": {
            "approve": False,
            "revise": False,
            "reject": False,
        },
        "metadata": {
            "created_at": proposal.created_at.isoformat(),
            "updated_at": proposal.updated_at.isoformat(),
        }
    }
    return packet


def store_approval(packet: Dict[str, Any], approved_by: str, approved_at: str) -> Dict[str, Any]:
    """
    Store approval information in the packet.
    """
    packet["approval"] = {
        "approved_by": approved_by,
        "approved_at": approved_at,
        "hash": packet["approval_hash"],
    }
    packet["controls"]["approve"] = True
    return packet


def is_approval_valid(original_packet: Dict[str, Any], current_proposal: Proposal) -> bool:
    """
    Check if the approval is still valid after potential edits to the proposal.
    """
    current_hash = generate_approval_hash(current_proposal)
    return current_hash == original_packet["approval_hash"]
