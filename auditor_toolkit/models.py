"""Versioned audit records. A completed check can contain defects."""

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

SCHEMA_VERSION = 2
COVERAGE_VERSION = 1
Status = Literal["ok", "error", "skipped"]

UNIMPLEMENTED_STATIC_CHECKS = frozenset({"hreflang", "language", "images", "social_meta"})
UNIMPLEMENTED_RENDERED_CHECKS = frozenset({"cookie_consent", "third_party", "browser_console"})
STATIC_REQUIRED_CHECKS = frozenset({
    "fetch", "page", "schema", "headers", "hygiene", "ux", "technology",
    "js_vulnerabilities", "structured_validation",
}) | UNIMPLEMENTED_STATIC_CHECKS
RENDERED_REQUIRED_CHECKS = frozenset({"browser", "axe", "pdf"}) | UNIMPLEMENTED_RENDERED_CHECKS


def required_check_ids(browser=False):
    return STATIC_REQUIRED_CHECKS | (RENDERED_REQUIRED_CHECKS if browser else frozenset())


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
        CheckDefinition("pdf", "reporting", "rendered"),
        CheckDefinition("technology", "technical"),
        CheckDefinition("js_vulnerabilities", "security"),
        CheckDefinition("structured_validation", "local"),
        CheckDefinition("hreflang", "seo", version="2", limitation="Not implemented"),
        CheckDefinition("language", "technical", version="2", limitation="Not implemented"),
        CheckDefinition("images", "performance", version="2", limitation="Not implemented"),
        CheckDefinition("social_meta", "technical", version="2", limitation="Not implemented"),
        CheckDefinition("cookie_consent", "privacy", mode="rendered", version="2", limitation="Not implemented"),
        CheckDefinition("third_party", "technical", mode="rendered", version="2", limitation="Not implemented"),
        CheckDefinition("browser_console", "technical", mode="rendered", version="2", limitation="Not implemented"),
        CheckDefinition("server_technology", "technical"),
    )
}


def coverage_summary(checks):
    required = sorted(name for name, check in checks.items() if check.get("required"))
    missing = [name for name in required if checks[name].get("status") != "ok"]
    return {
        "version": COVERAGE_VERSION,
        "required": len(required),
        "passed": len(required) - len(missing),
        "required_checks": required,
        "missing_checks": missing,
    }


def current_coverage_gaps(report):
    """Return required checks lacking current, explicit execution evidence.

    A historical ``complete`` label alone cannot establish present coverage.
    Check versions and the coverage contract make pre-placeholder-fix reports
    ineligible for cache reuse without changing their immutable saved records.
    """
    raw_checks = report.get("checks")
    raw_evidence = report.get("evidence")
    checks = {
        name: value for name, value in raw_checks.items() if isinstance(value, dict)
    } if isinstance(raw_checks, dict) else {}
    evidence = raw_evidence if isinstance(raw_evidence, dict) else {}
    coverage = report.get("coverage")
    coverage = coverage if isinstance(coverage, dict) else {}
    requested_browser = report.get("browser_requested")
    rendered_profile = report.get("profile") == "rendered"
    browser = rendered_profile or requested_browser is True
    mode_consistent = (
        "browser_requested" not in report
        or isinstance(requested_browser, bool)
        and not (rendered_profile and requested_browser is False)
    )
    required = required_check_ids(browser) | {
        name for name, check in checks.items() if check.get("required")
    }
    metadata_current = (
        report.get("schema_version") == SCHEMA_VERSION
        and mode_consistent
        and coverage.get("version") == COVERAGE_VERSION
        and coverage == coverage_summary(checks)
    )
    gaps = []
    for name in sorted(required):
        check = checks.get(name, {})
        observed = evidence.get(name, {})
        observed = observed if isinstance(observed, dict) else {}
        definition = REGISTRY.get(name)
        if (
            not metadata_current
            or check.get("required") is not True
            or check.get("status") != "ok"
            or definition is None
            or observed.get("check_version") != definition.version
            or observed.get("mode") != definition.mode
            or not observed.get("observed_at")
            or not observed.get("url")
            or not isinstance(observed.get("data"), dict)
        ):
            gaps.append(name)
    return gaps


def has_current_complete_coverage(report):
    return report.get("status") == "complete" and not current_coverage_gaps(report)
