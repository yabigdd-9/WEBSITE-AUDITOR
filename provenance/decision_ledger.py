"""
Decision ledger: append-only log of consequential decisions.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import hashlib
import json

@dataclass
class DecisionLedgerEntry:
    decision_id: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    entity_type: str
    entity_id: str
    state_before: str
    action: str
    reason: str
    evidence_refs: List[str] = field(default_factory=list)
    confidence: float = 0.0
    policy_version: str = ""
    idempotency_key: str = ""
    state_after: str = ""
    result: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "timestamp": self.timestamp,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "state_before": self.state_before,
            "action": self.action,
            "reason": self.reason,
            "evidence_refs": self.evidence_refs,
            "confidence": self.confidence,
            "policy_version": self.policy_version,
            "idempotency_key": self.idempotency_key,
            "state_after": self.state_after,
            "result": self.result,
        }

class DecisionLedger:
    def __init__(self):
        self.entries: List[DecisionLedgerEntry] = []

    def add_entry(self, entry: DecisionLedgerEntry):
        self.entries.append(entry)

    def get_entries(self) -> List[DecisionLedgerEntry]:
        return self.entries.copy()

    def to_list(self) -> List[Dict[str, Any]]:
        return [entry.to_dict() for entry in self.entries]