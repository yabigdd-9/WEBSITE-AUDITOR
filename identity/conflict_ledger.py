"""
Conflict ledger for identity resolution.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

@dataclass
class ConflictEntry:
    conflict_id: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    entity_type: str
    entity1_id: str
    entity2_id: str
    conflict_type: str  # e.g., 'authoritative_conflict', 'data_contradiction'
    description: str
    resolved: bool = False
    resolution: Optional[str] = None

    def to_dict(self):
        return {
            "conflict_id": self.conflict_id,
            "timestamp": self.timestamp,
            "entity_type": self.entity_type,
            "entity1_id": self.entity1_id,
            "entity2_id": self.entity2_id,
            "conflict_type": self.conflict_type,
            "description": self.description,
            "resolved": self.resolved,
            "resolution": self.resolution,
        }

class ConflictLedger:
    def __init__(self):
        self.conflicts: List[ConflictEntry] = []

    def add_conflict(self, entry: ConflictEntry):
        self.conflicts.append(entry)

    def get_conflicts(self, unresolved_only: bool = False) -> List[ConflictEntry]:
        if unresolved_only:
            return [c for c in self.conflicts if not c.resolved]
        return self.conflicts.copy()