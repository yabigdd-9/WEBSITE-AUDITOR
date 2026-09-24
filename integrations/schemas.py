"""Strict, dependency-free event and handoff schemas."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import re
from typing import Any
from uuid import uuid4

EVENT_TYPES = frozenset({
    "prospect.discovered", "prospect.qualified", "audit.requested", "audit.started",
    "audit.completed", "audit.failed", "evidence.ready", "proof.ready", "quote.ready",
    "draft.ready", "review.required", "job.started", "job.completed", "job.failed",
    "provider.rate_limited", "provider.recovered", "agent.started", "agent.completed",
    "agent.failed", "github.pr_opened", "github.ci_failed", "github.ci_passed",
})
JOB_STATUSES = frozenset({"pending", "leased", "running", "completed", "failed", "cancelled", "review_required"})
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


def _identifier(value: Any, name: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{name} must be a bounded identifier")
    return value


@dataclass(frozen=True)
class EventEnvelope:
    event_id: str
    type: str
    source: str
    created_at: str
    correlation_id: str
    payload: dict[str, Any]
    schema_version: int = 1

    @classmethod
    def parse(cls, value: Any) -> "EventEnvelope":
        required = {"event_id", "type", "source", "created_at", "correlation_id", "payload", "schema_version"}
        if not isinstance(value, dict) or set(value) != required:
            raise ValueError("Event envelope fields must match schema exactly")
        if type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("Unsupported event schema_version")
        if value["type"] not in EVENT_TYPES:
            raise ValueError("Unsupported event type")
        if not isinstance(value["payload"], dict) or len(str(value["payload"])) > 100_000:
            raise ValueError("payload must be an object under 100 KB")
        try:
            parsed = datetime.fromisoformat(value["created_at"].replace("Z", "+00:00"))
        except (ValueError, AttributeError) as exc:
            raise ValueError("created_at must be an ISO-8601 timestamp") from exc
        if parsed.tzinfo is None:
            raise ValueError("created_at must include a timezone")
        return cls(_identifier(value["event_id"], "event_id"), value["type"],
                   _identifier(value["source"], "source"), parsed.isoformat(),
                   _identifier(value["correlation_id"], "correlation_id"),
                   value["payload"], 1)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def create(cls, event_type: str, source: str, payload: dict[str, Any], correlation_id: str | None = None):
        return cls.parse({"event_id": str(uuid4()), "type": event_type, "source": source,
                          "created_at": datetime.now(timezone.utc).isoformat(),
                          "correlation_id": correlation_id or str(uuid4()), "payload": payload,
                          "schema_version": 1})


@dataclass(frozen=True)
class JobHandoff:
    job_id: str
    parent_job_id: str | None
    task_type: str
    objective: str
    repository: str
    assigned_to: str
    constraints: dict[str, Any]
    artifacts: list[str] = field(default_factory=list)
    status: str = "pending"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    retries: int = 0
    provenance: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def parse(cls, value: Any) -> "JobHandoff":
        required = {"job_id", "parent_job_id", "task_type", "objective", "repository", "assigned_to",
                    "constraints", "artifacts", "status", "created_at", "updated_at", "retries", "provenance"}
        if not isinstance(value, dict) or set(value) != required:
            raise ValueError("Job fields must match schema exactly")
        for key in ("job_id", "task_type", "repository", "assigned_to"):
            _identifier(value[key], key)
        _identifier(value["parent_job_id"], "parent_job_id", optional=True)
        if not isinstance(value["objective"], str) or not value["objective"].strip() or len(value["objective"]) > 4000:
            raise ValueError("objective must contain 1..4000 characters")
        if not isinstance(value["constraints"], dict) or not isinstance(value["provenance"], dict):
            raise ValueError("constraints and provenance must be objects")
        if not isinstance(value["artifacts"], list) or any(not isinstance(x, str) or len(x) > 1000 for x in value["artifacts"]):
            raise ValueError("artifacts must be a list of bounded strings")
        if value["status"] not in JOB_STATUSES:
            raise ValueError("Unsupported job status")
        if type(value["retries"]) is not int or not 0 <= value["retries"] <= 100:
            raise ValueError("retries must be an integer from 0 to 100")
        for key in ("created_at", "updated_at"):
            try:
                parsed = datetime.fromisoformat(value[key].replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError
            except (ValueError, AttributeError) as exc:
                raise ValueError(f"{key} must be timezone-aware ISO-8601") from exc
        safety = value["constraints"]
        if safety.get("paid_allowed", False) is not False or safety.get("max_cost_usd", 0) != 0:
            raise ValueError("Paid routes are prohibited: paid_allowed=false and max_cost_usd=0 required")
        if any(safety.get(key, False) for key in ("send", "deploy", "purchase")):
            raise ValueError("send, deploy, and purchase require separate human approval")
        return cls(**value)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
