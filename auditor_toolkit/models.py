"""Versioned audit records. A completed check can contain defects."""

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

SCHEMA_VERSION = 2
Status = Literal["ok", "error", "skipped"]


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
        CheckDefinition("hygiene", "technical"),
        CheckDefinition("links", "technical"),
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
        CheckDefinition(
            "flow",
            "conversion",
            "rendered",
            limitation="No form submission or synthetic inquiry; booking/payment side effects prohibited.",
        ),
        CheckDefinition("pdf", "reporting", "rendered"),
    )
}
