"""Versioned audit records. A completed check can contain defects."""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Literal

SCHEMA_VERSION = 2
Status = Literal["ok", "error", "skipped"]


class RiskValue(Enum):
    """Severity levels for risks and findings."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class Risk:
    """Risk assessment with severity and numeric score.

    Attributes:
        value: Severity level (low, medium, high, critical).
        score: Numeric score for aggregation (typically 4, 8, 16, 30).
    """

    value: RiskValue
    score: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {"value": self.value.value, "score": self.score}


@dataclass
class Action:
    """Remediation action with metadata for execution tracking.

    Attributes:
        action_id: Unique identifier for this action.
        name: Human-readable action name.
        category: Action category (e.g., "technical", "content", "security").
        risk: Risk assessment for this action.
        connector: Integration connector (e.g., "local", "email", "webhook").
        domain: Target domain for the action.
        environment: Target environment (e.g., "production", "staging").
        requires_approval: Whether human approval is required before execution.
        requires_authorization: Whether external authorization is required.
        payload: Arbitrary action-specific data.
        idempotency_key: Key for deduplicating repeated action requests.
    """

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
    def from_dict(cls, data: dict[str, Any]) -> "Action":
        """Deserialize from dictionary."""
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
        """Serialize to dictionary."""
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
    """Definition of an audit check.

    Attributes:
        id: Unique check identifier (e.g., "fetch", "page", "headers").
        category: Check category (e.g., "technical", "seo", "security").
        mode: Execution mode ("static" or "rendered").
        version: Check version string.
        evidence_required: Whether evidence must be collected.
        limitation: Human-readable limitation/disclaimer for this check.
    """

    id: str
    category: str
    mode: str = "static"
    version: str = "1"
    evidence_required: bool = True
    limitation: str = ""


@dataclass
class CheckResult:
    """Result of a single check execution.

    Attributes:
        status: One of "ok", "error", "skipped".
        reason: Error or skip reason (empty on success).
        required: Whether this check is required for overall pass.
        elapsed_ms: Execution time in milliseconds.
    """

    status: Status
    reason: str = ""
    required: bool = True
    elapsed_ms: int = 0


@dataclass
class Evidence:
    """Evidence collected during a check.

    Attributes:
        url: Target URL that was checked.
        observed_at: ISO timestamp when evidence was collected.
        mode: Check mode ("static" or "rendered").
        data: Check-specific evidence data.
        tool_version: Version of the tool that collected this evidence.
    """

    url: str
    observed_at: str
    mode: str
    data: dict[str, Any] = field(default_factory=dict)
    tool_version: str = "2"


@dataclass
class Page:
    """Crawled page information.

    Attributes:
        url: Page URL.
        status_code: HTTP status code.
        depth: Crawl depth from start URL.
        links: Discovered internal links on this page.
    """

    url: str
    status_code: int
    depth: int = 0
    links: list[str] = field(default_factory=list)


@dataclass
class Artifact:
    """Generated artifact metadata.

    Attributes:
        path: Filesystem path to the artifact.
        sha256: SHA256 hash of the artifact content.
        size: Artifact size in bytes.
    """

    path: str
    sha256: str
    size: int


@dataclass
class Remediation:
    """Finding remediation tracking.

    Attributes:
        finding_id: Associated finding identifier.
        state: Current remediation state (see STATES in storage.py).
        owner: Assigned owner/assignee.
        due_date: Target completion date (ISO format).
        fix_reference: Reference to fix (commit, ticket, etc.).
        last_verified: Timestamp of last verification run.
    """

    finding_id: str
    state: str = "detected"
    owner: str = ""
    due_date: str = ""
    fix_reference: str = ""
    last_verified: str | None = None


@dataclass
class AuditRun:
    """Complete audit run record.

    Attributes:
        run_id: Unique run identifier.
        url: Audited URL.
        timestamp: ISO timestamp of audit start.
        status: Overall status ("complete" or "partial").
        checks: Dictionary of check results.
        defects: List of finding dictionaries.
        schema_version: Audit schema version.
    """

    run_id: str
    url: str
    timestamp: str
    status: str
    checks: dict[str, Any]
    defects: list[dict[str, Any]]
    schema_version: int = SCHEMA_VERSION

    def to_dict(self):
        """Serialize to dictionary."""
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
        CheckDefinition("technology", "technical"),
        CheckDefinition("js_vulnerabilities", "security"),
        CheckDefinition("structured_validation", "local"),
        CheckDefinition("server_technology", "technical"),
    )
}
