"""
Proposal schema definition for the WEBSITE-AUDITOR proposal engine.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum


class ProposalStatus(Enum):
    NOT_READY = "NOT_READY"
    SCOPE_READY = "SCOPE_READY"
    ESTIMATE_READY = "ESTIMATE_READY"
    PROPOSAL_DRAFTED = "PROPOSAL_DRAFTED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    HUMAN_APPROVED = "HUMAN_APPROVED"
    REVISED = "REVISED"
    ARCHIVED = "ARCHIVED"


class ProposalVersionState(Enum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


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
    effort_band: str
    dependencies: List[str]
    risk: str
    finding_ids: List[str]


@dataclass
class Proposal:
    proposal_id: str
    business_id: str
    website_id: str
    opportunity_id: str
    proof_id: str
    proposal_version: str
    pricing_version: str
    currency: str
    scope_items: List[ScopeItem]
    deliverables: List[str]
    effort: str
    estimate_band: str
    assumptions: List[str]
    exclusions: List[str]
    acceptance_criteria: List[str]
    optional_addons: List[str]
    evidence_refs: List[str]
    limitations: List[str]
    status: ProposalStatus
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    version_state: ProposalVersionState = field(default=ProposalVersionState.DRAFT)

    def update_timestamp(self):
        self.updated_at = datetime.now()