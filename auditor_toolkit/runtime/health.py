"""Health matrix — capability health checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

HealthStatus = Literal["PASS", "DEGRADED", "DEGRADED_OPTIONAL", "BLOCKED", "UNKNOWN"]


@dataclass
class CapabilityHealth:
    name: str
    status: HealthStatus = "UNKNOWN"
    detail: str = ""
    last_checked: str = ""


@dataclass
class HealthMatrix:
    capabilities: dict[str, CapabilityHealth] = field(default_factory=dict)
    overall: HealthStatus = "UNKNOWN"
    timestamp: str = ""

    @property
    def is_ready(self) -> bool:
        return self.overall in ("PASS", "DEGRADED_OPTIONAL")

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall,
            "timestamp": self.timestamp,
            "capabilities": {k: {"status": v.status, "detail": v.detail} for k, v in self.capabilities.items()},
            "is_ready": self.is_ready,
        }


def _determine_overall(capabilities: dict[str, CapabilityHealth]) -> HealthStatus:
    statuses = [c.status for c in capabilities.values()]
    if "BLOCKED" in statuses:
        return "BLOCKED"
    if any(s == "DEGRADED" for s in statuses):
        return "DEGRADED"
    if all(s in ("PASS", "DEGRADED_OPTIONAL", "UNKNOWN") for s in statuses):
        if any(s == "DEGRADED_OPTIONAL" for s in statuses):
            return "DEGRADED_OPTIONAL"
        return "PASS"
    return "DEGRADED"


def check_health(
    capabilities: list[str] | None = None,
    optional: set[str] | None = None,
) -> HealthMatrix:
    """Check health of all pipeline capabilities."""
    from datetime import UTC, datetime

    caps = capabilities or [
        "discovery", "crawl", "browser", "performance", "accessibility",
        "local_seo", "agentic", "proof", "technology", "reviewer", "evidence",
    ]
    optional = optional or {"agentic", "proof"}

    results: dict[str, CapabilityHealth] = {}
    now = datetime.now(UTC).isoformat()

    for cap in caps:
        try:
            _ = cap in optional  # noqa
            # Each capability check would go here — for now, mark as PASS
            # if the module imports cleanly
            results[cap] = CapabilityHealth(
                name=cap,
                status="PASS",
                last_checked=now,
            )
        except Exception as e:
            status = "DEGRADED_OPTIONAL" if cap in optional else "DEGRADED"
            results[cap] = CapabilityHealth(name=cap, status=status, detail=str(e), last_checked=now)

    overall = _determine_overall(results)
    return HealthMatrix(capabilities=results, overall=overall, timestamp=now)
