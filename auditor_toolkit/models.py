"""Versioned audit records. A completed check can contain defects."""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Literal

SCHEMA_VERSION = 2
Status = Literal["ok", "error", "skipped"]


class RiskValue(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class Risk:
    value: RiskValue
    score: int

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value.value, "score": self.score}


@dataclass
class Action:
    action_id: str
    name: str
    category: str
    risk: Risk
    connector: str
    domain: str
    environment: str
    requires_approval: bool = False
    requires_authorization: bool = False
    payload: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'Action':
        return cls(
            action_id=data.get("action_id", ""),
            name=data.get("name", ""),
            category=data["category"],
            environment=data["environment"],
            risk=Risk(RiskValue(data["risk"]["value"]), data["risk"]["score"]),
            connector=data.get("connector", "local"),
            domain=data.get("domain", ""),
            requires_approval=data.get("requires_approval", False),
            requires_authorization=data.get("requires_authorization", False),
            payload=data.get("payload", {}),
            idempotency_key=data.get("idempotency_key", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "name": self.name,
            "category": self.category,
            "risk": self.risk.to_dict(),
            "connector": self.connector,
            "domain": self.domain,
            "environment": self.environment,
            "requires_approval": self.requires_approval,
            "requires_authorization": self.requires_authorization,
            "payload": self.payload,
            "idempotency_key": self.idempotency_key,
        }



@dataclass(frozen=True)
class CheckDefinition:
    id: str
    category: str
    mode: str = "static"
    version: str = "1"
    evidence_required: bool = True
    limitation: str = ""


@dataclass
class CheckResult:
    status: Status
    reason: str = ""
    required: bool = True
    elapsed_ms: int = 0


@dataclass
class Evidence:
    url: str
    observed_at: str
    mode: str
    data: dict[str, Any] = field(default_factory=dict)
    tool_version: str = "2"


@dataclass
class Page:
    url: str
    status_code: int
    depth: int = 0
    links: list[str] = field(default_factory=list)


@dataclass
class Artifact:
    path: str
    sha256: str
    size: int


@dataclass
class Remediation:
    finding_id: str
    state: str = "detected"
    owner: str = ""
    due_date: str = ""
    fix_reference: str = ""
    last_verified: str | None = None


@dataclass
class AuditRun:
    run_id: str
    url: str
    timestamp: str
    status: str
    checks: dict[str, Any]
    defects: list[dict[str, Any]]
    schema_version: int = SCHEMA_VERSION

    def to_dict(self):
        return asdict(self)


REGISTRY = {
    d.id: d
    for d in (
        CheckDefinition("fetch", "technical"),
        CheckDefinition(
            "page",
            "seo",
            limitation="Content and conversion observations require editorial review.",
        ),
        CheckDefinition(
            "schema",
            "local",
            limitation="Presence does not establish eligibility or business identity.",
        ),
        CheckDefinition(
            "accessibility_static",
            "accessibility",
            limitation="Static checks do not establish conformance.",
        ),
        CheckDefinition(
            "ux", "privacy", limitation="Observed behavior is not a legal determination."
        ),
        CheckDefinition("headers", "security"),
        CheckDefinition(
            "hygiene",
            "technical",
            limitation="Deterministic robots, sitemap, header and mixed-content checks.",
        ),
        CheckDefinition(
            "links",
            "technical",
            limitation="Bounded same-origin link validation; not an exhaustive crawler.",
        ),
        CheckDefinition("tls", "security"),
        CheckDefinition("dns", "technical"),
        CheckDefinition("crawl", "technical"),
        CheckDefinition(
            "lychee",
            "technical",
            limitation="External local CLI check; bounded by Lychee configuration and network conditions.",
        ),
        CheckDefinition(
            "lighthouse",
            "performance",
            "rendered",
            limitation="Laboratory result; not field Core Web Vitals.",
        ),
        CheckDefinition(
            "browser",
            "performance",
            "rendered",
            limitation="Laboratory observations, not field Core Web Vitals.",
        ),
        CheckDefinition(
            "axe",
            "accessibility",
            "rendered",
            limitation="Manual keyboard, screen-reader and content review remains necessary.",
        ),
        CheckDefinition("pdf", "reporting", "rendered"),
    )
}
