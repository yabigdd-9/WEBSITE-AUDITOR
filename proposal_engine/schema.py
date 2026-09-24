"""
Proposal schema for the WEBSITE-AUDITOR proposal engine.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class ScopeItem:
    scope_id: str
    title: str
    problem: str
    evidence: str
    affected_urls: List[str]
    root_cause: str
    proposed_work: str
    deliverables: List[str]
    verification: str
    effort_band: str  # XS, S, M, L, XL, UNKNOWN
    dependencies: List[str] = field(default_factory=list)
    risk: str = "LOW"  # LOW, MEDIUM, HIGH
    finding_ids: List[str] = field(default_factory=list)


@dataclass
class Proposal:
    proposal_id: str
    business_id: str
    website_id: str
    opportunity_id: str
    proof_id: str
    proposal_version: int = 1
    pricing_version: int = 1
    currency: str = "NZD"
    scope_items: List[ScopeItem] = field(default_factory=list)
    deliverables: List[str] = field(default_factory=list)
    effort: str = ""  # effort band or string
    estimate_band: str = ""  # e.g., "XS-S", "M-L"
    assumptions: List[str] = field(default_factory=list)
    exclusions: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    optional_addons: List[str] = field(default_factory=list)
    evidence_refs: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    status: str = "NOT_READY"  # NOT_READY, SCOPE_READY, ESTIMATE_READY, PROPOSAL_DRAFTED, HUMAN_REVIEW_REQUIRED, HUMAN_APPROVED, REVISED, ARCHIVED
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def update_timestamp(self):
        self.updated_at = datetime.now()

    def new_version(self) -> 'Proposal':
        """Create a new version of this proposal with incremented proposal_version."""
        return Proposal(
            proposal_id=self.proposal_id,
            business_id=self.business_id,
            website_id=self.website_id,
            opportunity_id=self.opportunity_id,
            proof_id=self.proof_id,
            proposal_version=self.proposal_version + 1,
            pricing_version=self.pricing_version,
            currency=self.currency,
            scope_items=self.scope_items.copy(),
            deliverables=self.deliverables.copy(),
            effort=self.effort,
            estimate_band=self.estimate_band,
            assumptions=self.assumptions.copy(),
            exclusions=self.exclusions.copy(),
            acceptance_criteria=self.acceptance_criteria.copy(),
            optional_addons=self.optional_addons.copy(),
            evidence_refs=self.evidence_refs.copy(),
            limitations=self.limitations.copy(),
            status=self.status,
            created_at=self.created_at,
            updated_at=datetime.now()
        )
