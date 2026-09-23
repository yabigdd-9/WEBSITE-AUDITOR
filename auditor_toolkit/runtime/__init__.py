"""Production Integration + Reliability + 7-Day Soak.

v41 adds the runtime supervision layer: preflight gates, health monitoring,
recovery policies, circuit breakers, quarantine/DLQ, idempotency, resource
limits, graceful shutdown, and soak testing.
"""

from .health import HealthMatrix, check_health
from .readiness import PreflightResult, run_preflight

__all__ = [
    "PreflightResult",
    "run_preflight",
    "HealthMatrix",
    "check_health",
]
