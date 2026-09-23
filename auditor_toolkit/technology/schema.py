"""Canonical data models for technology detection, version tracking, and vulnerability advisories.

All schema types are immutable (frozen=True) and serialisable via to_dict().
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Severity levels
# ---------------------------------------------------------------------------

SeverityLevel = Literal["critical", "high", "medium", "low"]

# ---------------------------------------------------------------------------
# Technology detection result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TechDetection:
    """Single technology detection with confidence score."""

    name: str
    category: str  # cms, framework, language, server, analytics, cdn, payment, ecommerce, hosting
    confidence: float = 1.0
    evidence: str = ""  # What pattern matched

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# TechFingerprint — aggregated detection for one page/site
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TechFingerprint:
    """Aggregated technology fingerprint for a single audit target."""

    cms: TechDetection | None = None
    framework: TechDetection | None = None
    language: TechDetection | None = None
    server: TechDetection | None = None
    analytics: list[TechDetection] = field(default_factory=list)
    cdn: TechDetection | None = None
    payment: list[TechDetection] = field(default_factory=list)
    ecommerce: TechDetection | None = None
    hosting: TechDetection | None = None

    # Convenience: flat list of all detections
    @property
    def all_detections(self) -> list[TechDetection]:
        items: list[TechDetection] = []
        for attr in (
            "cms", "framework", "language", "server", "cdn", "ecommerce", "hosting",
        ):
            val = getattr(self, attr)
            if val:
                items.append(val)
        items.extend(self.analytics)
        items.extend(self.payment)
        return items

    def to_dict(self) -> dict[str, Any]:
        def _td(d: TechDetection | None) -> dict[str, Any] | None:
            return d.to_dict() if d else None

        return {
            "cms": _td(self.cms),
            "framework": _td(self.framework),
            "language": _td(self.language),
            "server": _td(self.server),
            "analytics": [d.to_dict() for d in self.analytics],
            "cdn": _td(self.cdn),
            "payment": [d.to_dict() for d in self.payment],
            "ecommerce": _td(self.ecommerce),
            "hosting": _td(self.hosting),
        }


# ---------------------------------------------------------------------------
# TechStack — full stack summary including version info
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TechStack:
    """Full technology stack with version and vulnerability information."""

    fingerprint: TechFingerprint
    versions: list[VersionInfo] = field(default_factory=list)
    vulnerabilities: list[VulnerabilityAdvisory] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint.to_dict(),
            "versions": [v.to_dict() for v in self.versions],
            "vulnerabilities": [v.to_dict() for v in self.vulnerabilities],
        }


# ---------------------------------------------------------------------------
# VersionInfo — version status for a single component
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VersionInfo:
    """Version information for a detected technology component."""

    name: str
    detected_version: str = ""
    latest_version: str = ""
    is_outdated: bool = False
    severity: SeverityLevel = "low"  # how severe the outdated status is
    evidence: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# VulnerabilityAdvisory — CVE / security advisory for outdated component
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VulnerabilityAdvisory:
    """Vulnerability advisory for an outdated or vulnerable component."""

    component: str
    version: str = ""
    severity: SeverityLevel = "medium"
    description: str = ""
    remediation: str = ""
    source: str = "embedded_advisory_db"
    detected_at: str = ""
    cve_id: str = ""  # optional — empty if no CVE assigned

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# TechEnrichmentResult — pipeline output
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TechEnrichmentResult:
    """Result of the full technology enrichment pipeline."""

    url: str
    fingerprint: TechFingerprint
    versions: list[VersionInfo] = field(default_factory=list)
    vulnerabilities: list[VulnerabilityAdvisory] = field(default_factory=list)
    run_id: str = ""
    started_at: str = ""
    completed_at: str = ""
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def tech_stack(self) -> TechStack:
        return TechStack(
            fingerprint=self.fingerprint,
            versions=self.versions,
            vulnerabilities=self.vulnerabilities,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": round(self.duration_seconds, 2),
            "fingerprint": self.fingerprint.to_dict(),
            "versions": [v.to_dict() for v in self.versions],
            "vulnerabilities": [v.to_dict() for v in self.vulnerabilities],
            "errors": self.errors,
            "warnings": self.warnings,
        }
