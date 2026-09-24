"""
Event envelope definition.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

@dataclass
class EventEnvelope:
    event_id: str
    event_type: str
    run_id: str
    trace_id: str
    entity_type: str
    entity_id: str
    actor: str
    occurred_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    payload: Dict[str, Any] = field(default_factory=dict)

    # Lifecycle: START, RUNNING, COMPLETE, ABORT, FAIL
    lifecycle: str = "START"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "actor": self.actor,
            "occurred_at": self.occurred_at,
            "payload": self.payload,
            "lifecycle": self.lifecycle,
        }