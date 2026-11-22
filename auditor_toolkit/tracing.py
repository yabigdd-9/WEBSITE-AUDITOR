"""OpenTelemetry tracing for auditor_toolkit.

Provides distributed tracing capabilities for audit runs and checks.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter as HTTPOTLPSpanExporter,
)
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Span, SpanKind, Status, StatusCode

logger = logging.getLogger(__name__)

# Global tracer
_tracer: trace.Tracer | None = None
_tracing_initialized = False


def init_tracing(
    service_name: str = "website-auditor",
    otlp_endpoint: str | None = None,
    otlp_protocol: str = "http",  # "http" or "grpc"
    console_export: bool = False,
    sample_rate: float = 1.0,
) -> trace.Tracer:
    """Initialize OpenTelemetry tracing.

    Args:
        service_name: Service name for traces.
        otlp_endpoint: OTLP endpoint (e.g., "localhost:4317" for gRPC,
            "http://localhost:4318/v1/traces" for HTTP).
        otlp_protocol: "http" or "grpc".
        console_export: Whether to also export to console.
        sample_rate: Sampling rate (0.0 to 1.0).

    Returns:
        Configured tracer instance.
    """
    global _tracer, _tracing_initialized

    if _tracing_initialized:
        return _tracer

    # Create resource
    resource = Resource.create({SERVICE_NAME: service_name})

    # Create tracer provider
    provider = TracerProvider(resource=resource)

    # Configure exporters
    exporters = []

    if otlp_endpoint:
        if otlp_protocol == "grpc":
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        else:
            exporter = HTTPOTLPSpanExporter(endpoint=otlp_endpoint)
        exporters.append(BatchSpanProcessor(exporter))
        logger.info(f"OTLP tracing configured: {otlp_endpoint} ({otlp_protocol})")

    if console_export or not otlp_endpoint:
        exporters.append(BatchSpanProcessor(ConsoleSpanExporter()))
        logger.info("Console tracing enabled")

    for processor in exporters:
        provider.add_span_processor(processor)

    # Set as global provider
    trace.set_tracer_provider(provider)

    # Create tracer
    _tracer = trace.get_tracer(__name__)
    _tracing_initialized = True

    logger.info(f"Tracing initialized for service: {service_name}")
    return _tracer


def get_tracer() -> trace.Tracer | None:
    """Get the current tracer."""
    global _tracer
    if _tracer is None:
        # Auto-initialize with console export if not configured
        _tracer = init_tracing(console_export=True)
    return _tracer


def is_tracing_enabled() -> bool:
    """Check if tracing is initialized."""
    return _tracing_initialized


# ─── Span Helpers ───

@contextmanager
def audit_span(
    run_id: str,
    url: str,
    profile: str,
    attributes: dict[str, Any] | None = None,
):
    """Create a span for an audit run."""
    tracer = get_tracer()
    if tracer is None:
        yield None
        return

    attrs = {
        "audit.run_id": run_id,
        "audit.url": url,
        "audit.profile": profile,
        "audit.type": "full_audit",
    }
    if attributes:
        attrs.update(attributes)

    with tracer.start_as_current_span(
        f"audit:{profile}",
        kind=SpanKind.INTERNAL,
        attributes=attrs,
    ) as span:
        try:
            yield span
        except Exception as e:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise


@contextmanager
def check_span(
    check_name: str,
    run_id: str,
    url: str,
    attributes: dict[str, Any] | None = None,
):
    """Create a span for an individual check."""
    tracer = get_tracer()
    if tracer is None:
        yield None
        return

    attrs = {
        "check.name": check_name,
        "audit.run_id": run_id,
        "audit.url": url,
    }
    if attributes:
        attrs.update(attributes)

    with tracer.start_as_current_span(
        f"check:{check_name}",
        kind=SpanKind.INTERNAL,
        attributes=attrs,
    ) as span:
        try:
            yield span
        except Exception as e:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise


@contextmanager
def http_span(
    method: str,
    url: str,
    host: str,
    attributes: dict[str, Any] | None = None,
):
    """Create a span for an HTTP request."""
    tracer = get_tracer()
    if tracer is None:
        yield None
        return

    attrs = {
        "http.method": method,
        "http.url": url,
        "http.host": host,
        "net.peer.name": host,
    }
    if attributes:
        attrs.update(attributes)

    with tracer.start_as_current_span(
        f"HTTP {method} {host}",
        kind=SpanKind.CLIENT,
        attributes=attrs,
    ) as span:
        try:
            yield span
        except Exception as e:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise


@contextmanager
def external_api_span(
    api_name: str,
    attributes: dict[str, Any] | None = None,
):
    """Create a span for an external API call."""
    tracer = get_tracer()
    if tracer is None:
        yield None
        return

    attrs = {
        "external.api.name": api_name,
    }
    if attributes:
        attrs.update(attributes)

    with tracer.start_as_current_span(
        f"external:{api_name}",
        kind=SpanKind.CLIENT,
        attributes=attrs,
    ) as span:
        try:
            yield span
        except Exception as e:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise


def add_span_event(span: Span | None, name: str, attributes: dict[str, Any] | None = None):
    """Add an event to a span."""
    if span is not None:
        span.add_event(name, attributes or {})


def set_span_attribute(span: Span | None, key: str, value: Any):
    """Set an attribute on a span."""
    if span is not None:
        span.set_attribute(key, value)


def record_span_exception(span: Span | None, exception: Exception):
    """Record an exception on a span."""
    if span is not None:
        span.record_exception(exception)
        span.set_status(Status(StatusCode.ERROR, str(exception)))


# ─── Decorators ───

def traced_check(check_name: str):
    """Decorator to trace a check function."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Extract run_id and url from context or args
            run_id = kwargs.get("run_id", "unknown")
            url = kwargs.get("url", "unknown")

            with check_span(check_name, run_id, url) as span:
                result = func(*args, **kwargs)

                # Add result info to span
                if isinstance(result, tuple) and len(result) >= 2:
                    findings, evidence = result
                    add_span_event(span, "check_complete", {
                        "findings_count": len(findings) if findings else 0,
                        "has_evidence": evidence is not None,
                    })

                return result
        return wrapper
    return decorator

def traced_http(func):
    """Decorator to trace an HTTP request function."""
    def wrapper(*args, **kwargs):
        url = args[0] if args else kwargs.get("url", "unknown")
        method = kwargs.get("method", "GET")
        from urllib.parse import urlparse
        host = urlparse(url).hostname or "unknown"

        with http_span(method, url, host) as span:
            result = func(*args, **kwargs)

            if hasattr(result, "status_code"):
                set_span_attribute(span, "http.status_code", result.status_code)
                add_span_event(span, "http_response", {
                    "status_code": result.status_code,
                })

            return result
    return wrapper


# ─── Configuration from Environment ───

def init_tracing_from_env() -> trace.Tracer | None:
    """Initialize tracing from environment variables.

    Environment variables:
        WA_TRACING_ENABLED: "true" to enable (default: false)
        WA_TRACING_OTLP_ENDPOINT: OTLP endpoint
        WA_TRACING_OTLP_PROTOCOL: "http" or "grpc" (default: http)
        WA_TRACING_CONSOLE_EXPORT: "true" to enable console export
        WA_TRACING_SAMPLE_RATE: Sampling rate 0.0-1.0 (default: 1.0)
        WA_TRACING_SERVICE_NAME: Service name (default: website-auditor)
    """
    if os.getenv("WA_TRACING_ENABLED", "false").lower() != "true":
        return None

    return init_tracing(
        service_name=os.getenv("WA_TRACING_SERVICE_NAME", "website-auditor"),
        otlp_endpoint=os.getenv("WA_TRACING_OTLP_ENDPOINT"),
        otlp_protocol=os.getenv("WA_TRACING_OTLP_PROTOCOL", "http"),
        console_export=os.getenv("WA_TRACING_CONSOLE_EXPORT", "false").lower() == "true",
        sample_rate=float(os.getenv("WA_TRACING_SAMPLE_RATE", "1.0")),
    )


# ─── Integration with Pipeline ───

class TracedAuditContext:
    """Context manager for traced audit execution."""

    def __init__(self, run_id: str, url: str, profile: str):
        self.run_id = run_id
        self.url = url
        self.profile = profile
        self.span: Span | None = None
        self.check_spans: dict[str, Span] = {}

    def __enter__(self):
        tracer = get_tracer()
        if tracer:
            self.span = tracer.start_span(
                f"audit:{self.profile}",
                kind=SpanKind.INTERNAL,
                attributes={
                    "audit.run_id": self.run_id,
                    "audit.url": self.url,
                    "audit.profile": self.profile,
                },
            )
            self.span.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.span:
            if exc_type:
                self.span.record_exception(exc_val)
                self.span.set_status(Status(StatusCode.ERROR, str(exc_val)))
            self.span.__exit__(exc_type, exc_val, exc_tb)

    def start_check(self, check_name: str) -> Span | None:
        """Start a check span."""
        tracer = get_tracer()
        if tracer:
            span = tracer.start_span(
                f"check:{check_name}",
                kind=SpanKind.INTERNAL,
                attributes={
                    "check.name": check_name,
                    "audit.run_id": self.run_id,
                    "audit.url": self.url,
                },
            )
            span.__enter__()
            self.check_spans[check_name] = span
            return span
        return None

    def end_check(self, check_name: str, status: str = "ok", findings_count: int = 0):
        """End a check span."""
        span = self.check_spans.pop(check_name, None)
        if span:
            set_span_attribute(span, "check.status", status)
            set_span_attribute(span, "check.findings_count", findings_count)
            if status != "ok":
                span.set_status(Status(StatusCode.ERROR, f"Check {status}"))
            span.__exit__(None, None, None)

    def add_event(self, name: str, attributes: dict[str, Any] | None = None):
        """Add event to main audit span."""
        if self.span:
            add_span_event(self.span, name, attributes)
