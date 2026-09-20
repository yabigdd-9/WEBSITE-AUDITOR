"""Typed dataclasses for the policy-controlled action engine."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(prefix: str, parts: list[str]) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


class Risk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Mode(str, Enum):
    DISABLED = "disabled"
    DRY_RUN = "dry_run"
    SUPERVISED = "supervised"
    AUTONOMOUS = "autonomous"
    EMERGENCY_STOP = "emergency_stop"


class ActionStatus(str, Enum):
    PROPOSED = "proposed"
    DRY_RUN = "dry_run"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    EXECUTED = "executed"
    SIMULATED = "simulated"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    BLOCKED = "blocked"
    VERIFIED = "verified"


@dataclass
class Action:
    action_id: str
    action_type: str
    name: str
    category: str
    risk: Risk
    connector: str
    domain: str
    environment: str = "local"
    status: ActionStatus = ActionStatus.PROPOSED
    requires_approval: bool = False
    requires_authorization: bool = True
    reversible: bool = False
    idempotency_key: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    verification_checks: list[str] = field(default_factory=list)
    rollback_action_id: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def touch(self) -> None:
        self.updated_at = utc_now()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["risk"] = self.risk.value
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Action":
        data = dict(data)
        data["risk"] = Risk(data["risk"])
        data["status"] = ActionStatus(data["status"])
        return cls(**data)

    @staticmethod
    def make_idempotency_key(domain: str, action_type: str, payload: dict[str, Any]) -> str:
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return stable_id("idem", [domain.lower(), action_type, payload_json])


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    effect: str
    reason: str
    requires_approval: bool = False
    requires_authorization: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
