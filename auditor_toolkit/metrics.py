"""Prometheus metrics endpoint for auditor_toolkit.

Provides a /metrics HTTP endpoint for Prometheus scraping.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

logger = logging.getLogger(__name__)


# ─── Metric Definitions ───

# Audit metrics
audit_runs_total = Counter(
    "wa_audit_runs_total",
    "Total number of audit runs",
    ["status", "profile"],
)

audit_duration_seconds = Histogram(
    "wa_audit_duration_seconds",
    "Audit run duration in seconds",
    ["profile"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600],
)

audit_health_score = Histogram(
    "wa_audit_health_score",
    "Audit health score distribution",
    ["profile"],
    buckets=[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
)

audit_defects_total = Counter(
    "wa_audit_defects_total",
    "Total defects found",
    ["severity", "category"],
)

audit_check_duration_seconds = Histogram(
    "wa_audit_check_duration_seconds",
    "Individual check duration in seconds",
    ["check_name", "status"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1, 5, 10, 30, 60],
)

# HTTP metrics
http_requests_total = Counter(
    "wa_http_requests_total",
    "Total HTTP requests made by fetcher",
    ["method", "status", "host"],
)

http_request_duration_seconds = Histogram(
    "wa_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "host"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1, 5, 10, 30],
)

http_response_size_bytes = Histogram(
    "wa_http_response_size_bytes",
    "HTTP response size in bytes",
    ["host"],
    buckets=[1024, 10240, 102400, 1048576, 10485760],
)

# Cache metrics
cache_hits_total = Counter(
    "wa_cache_hits_total",
    "Total cache hits",
    ["namespace"],
)

cache_misses_total = Counter(
    "wa_cache_misses_total",
    "Total cache misses",
    ["namespace"],
)

# Rate limiting metrics
rate_limit_delays_total = Counter(
    "wa_rate_limit_delays_total",
    "Total rate limit delays applied",
    ["host"],
)

rate_limit_delay_seconds = Histogram(
    "wa_rate_limit_delay_seconds",
    "Rate limit delay duration in seconds",
    ["host"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1, 5, 10],
)

# System metrics
active_audits = Gauge(
    "wa_active_audits",
    "Number of currently running audits",
)

disk_usage_bytes = Gauge(
    "wa_disk_usage_bytes",
    "Disk usage in bytes",
    ["path", "type"],  # type: total, used, free
)

memory_usage_bytes = Gauge(
    "wa_memory_usage_bytes",
    "Memory usage in bytes",
    ["type"],  # type: total, available, used
)

# External API metrics
external_api_requests_total = Counter(
    "wa_external_api_requests_total",
    "Total external API requests",
    ["api_name", "status"],
)

external_api_duration_seconds = Histogram(
    "wa_external_api_duration_seconds",
    "External API request duration in seconds",
    ["api_name"],
    buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 120],
)

# Error metrics
errors_total = Counter(
    "wa_errors_total",
    "Total errors by type",
    ["error_type", "component"],
)


@dataclass
class MetricsContext:
    """Context for recording metrics during an audit run."""

    run_id: str
    url: str
    profile: str
    start_time: float = field(default_factory=time.perf_counter)
    check_timers: dict[str, float] = field(default_factory=dict)

    def record_audit_complete(self, status: str, health_score: float | None, defect_count: int):
        """Record audit completion metrics."""
        duration = time.perf_counter() - self.start_time
        audit_runs_total.labels(status=status, profile=self.profile).inc()
        audit_duration_seconds.labels(profile=self.profile).observe(duration)
        if health_score is not None:
            audit_health_score.labels(profile=self.profile).observe(health_score)

    def record_check_start(self, check_name: str):
        """Record check start time."""
        self.check_timers[check_name] = time.perf_counter()

    def record_check_complete(self, check_name: str, status: str, findings: list = None):
        """Record check completion metrics."""
        if check_name in self.check_timers:
            duration = time.perf_counter() - self.check_timers.pop(check_name)
            audit_check_duration_seconds.labels(check_name=check_name, status=status).observe(duration)

        if findings:
            for finding in findings:
                severity = finding.get("severity", "unknown")
                category = finding.get("check", "unknown")
                audit_defects_total.labels(severity=severity, category=category).inc()

    def record_http_request(self, method: str, host: str, status: int, duration: float, size: int):
        """Record HTTP request metrics."""
        http_requests_total.labels(method=method, status=str(status), host=host).inc()
        http_request_duration_seconds.labels(method=method, host=host).observe(duration)
        http_response_size_bytes.labels(host=host).observe(size)

    def record_cache_hit(self, namespace: str):
        """Record cache hit."""
        cache_hits_total.labels(namespace=namespace).inc()

    def record_cache_miss(self, namespace: str):
        """Record cache miss."""
        cache_misses_total.labels(namespace=namespace).inc()

    def record_rate_limit_delay(self, host: str, delay: float):
        """Record rate limit delay."""
        rate_limit_delays_total.labels(host=host).inc()
        rate_limit_delay_seconds.labels(host=host).observe(delay)

    def record_external_api(self, api_name: str, status: str, duration: float):
        """Record external API call."""
        external_api_requests_total.labels(api_name=api_name, status=status).inc()
        external_api_duration_seconds.labels(api_name=api_name).observe(duration)

    def record_error(self, error_type: str, component: str):
        """Record error."""
        errors_total.labels(error_type=error_type, component=component).inc()


# Global metrics context (for CLI/single-run usage)
_current_context: MetricsContext | None = None


def get_current_context() -> MetricsContext | None:
    """Get the current metrics context."""
    return _current_context


def set_current_context(context: MetricsContext | None):
    """Set the current metrics context."""
    global _current_context
    _current_context = context


@contextmanager
def audit_metrics_context(run_id: str, url: str, profile: str):
    """Context manager for audit metrics."""
    context = MetricsContext(run_id=run_id, url=url, profile=profile)
    set_current_context(context)
    active_audits.inc()
    try:
        yield context
    finally:
        active_audits.dec()
        set_current_context(None)


def record_system_metrics():
    """Record current system metrics (disk, memory)."""
    import shutil
    import psutil

    # Disk usage for current directory
    total, used, free = shutil.disk_usage(".")
    disk_usage_bytes.labels(path=".", type="total").set(total)
    disk_usage_bytes.labels(path=".", type="used").set(used)
    disk_usage_bytes.labels(path=".", type="free").set(free)

    # Memory
    mem = psutil.virtual_memory()
    memory_usage_bytes.labels(type="total").set(mem.total)
    memory_usage_bytes.labels(type="available").set(mem.available)
    memory_usage_bytes.labels(type="used").set(mem.used)


# ─── FastAPI /metrics endpoint ───

def create_metrics_app():
    """Create a minimal FastAPI app with /metrics endpoint."""
    try:
        from fastapi import FastAPI, Response
    except ImportError:
        logger.warning("FastAPI not available, metrics endpoint not created")
        return None

    app = FastAPI(title="Website Auditor Metrics")

    @app.get("/metrics")
    async def metrics():
        # Update system metrics before serving
        try:
            record_system_metrics()
        except Exception as e:
            logger.warning(f"Failed to record system metrics: {e}")
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/health")
    async def health():
        return {"status": "healthy", "service": "website-auditor-metrics"}

    return app


def metrics_middleware(request, call_next):
    """ASGI middleware to record HTTP metrics."""
    import time

    _ = time.perf_counter()
    response = call_next(request)

    # Record request metrics
    http_requests_total.labels(
        method=request.method,
        status=str(response.status_code),
        host=request.url.hostname or "unknown",
    ).inc()

    return response


# ─── CLI Integration ───

def record_audit_metrics(
    run_id: str,
    url: str,
    profile: str,
    status: str,
    health_score: float | None,
    defects: list[dict],
    checks: dict,
    duration_ms: int,
):
    """Record all metrics for a completed audit (for CLI usage)."""
    duration_s = duration_ms / 1000.0
    audit_runs_total.labels(status=status, profile=profile).inc()
    audit_duration_seconds.labels(profile=profile).observe(duration_s)
    if health_score is not None:
        audit_health_score.labels(profile=profile).observe(health_score)

    for defect in defects:
        severity = defect.get("severity", "unknown")
        category = defect.get("check", "unknown")
        audit_defects_total.labels(severity=severity, category=category).inc()

    for check_name, check_data in checks.items():
        check_status = check_data.get("status", "unknown")
        elapsed_ms = check_data.get("elapsed_ms", 0)
        audit_check_duration_seconds.labels(
            check_name=check_name, status=check_status
        ).observe(elapsed_ms / 1000.0)


def serve_metrics(port: int = 9090, host: str = "127.0.0.1"):
    """Serve metrics endpoint (blocking)."""
    import uvicorn

    app = create_metrics_app()
    if app is None:
        logger.error("Cannot create metrics app - FastAPI not available")
        return 1

    logger.info(f"Starting metrics server on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(serve_metrics())