"""
Immutable version model for proposals.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
import hashlib
import json


class ProposalVersionState(Enum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


@dataclass(frozen=True)
class ProposalVersion:
    """
    Immutable version of a proposal.
    Once created, cannot be modified.
    """
    version_id: str
    proposal_id: str
    version_number: int
    state: ProposalVersionState
    data: Dict[str, Any]  # Serialized proposal data
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str = "system"
    parent_version_id: Optional[str] = None

    def __post_init__(self):
        # Generate version_id if not provided
        if not self.version_id:
            version_string = f"{self.proposal_id}:{self.version_number}:{self.state.value}:{self.created_at.isoformat()}"
            object.__setattr__(self, 'version_id',
                             hashlib.sha256(version_string.encode()).hexdigest()[:16])

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'version_id': self.version_id,
            'proposal_id': self.proposal_id,
            'version_number': self.version_number,
            'state': self.state.value,
            'data': self.data,
            'created_at': self.created_at.isoformat(),
            'created_by': self.created_by,
            'parent_version_id': self.parent_version_id
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProposalVersion':
        """Create from dictionary."""
        data_copy = data.copy()
        # Convert string back to enum
        data_copy['state'] = ProposalVersionState(data_copy['state'])
        # Convert string back to datetime
        data_copy['created_at'] = datetime.fromisoformat(data_copy['created_at'])
        return cls(**data_copy)


@dataclass
class ProposalVersionHistory:
    """Tracks the version history of a proposal."""
    proposal_id: str
    versions: List[ProposalVersion] = field(default_factory=list)
    current_version_id: Optional[str] = None

    def add_version(self, version: ProposalVersion):
        """Add a new version to the history."""
        # Check if version already exists
        if any(v.version_id == version.version_id for v in self.versions):
            raise ValueError(f"Version {version.version_id} already exists")

        self.versions.append(version)
        # Sort by version number
        self.versions.sort(key=lambda v: v.version_number)
        self.current_version_id = version.version_id

    def get_version(self, version_id: str) -> Optional[ProposalVersion]:
        """Get a specific version by ID."""
        for version in self.versions:
            if version.version_id == version_id:
                return version
        return None

    def get_current_version(self) -> Optional[ProposalVersion]:
        """Get the current version."""
        if self.current_version_id:
            return self.get_version(self.current_version_id)
        return None

    def get_versions_by_state(self, state: ProposalVersionState) -> List[ProposalVersion]:
        """Get all versions with a specific state."""
        return [v for v in self.versions if v.state == state]

    def get_latest_version(self) -> Optional[ProposalVersion]:
        """Get the latest version by version number."""
        if not self.versions:
            return None
        return max(self.versions, key=lambda v: v.version_number)

    def get_version_numbers(self) -> List[int]:
        """Get all version numbers."""
        return [v.version_number for v in self.versions]