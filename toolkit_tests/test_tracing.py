"""Tests for distributed tracing."""

import os
from unittest.mock import patch

import pytest

from auditor_toolkit.tracing import (
    TracedAuditContext,
    add_span_event,
    audit_span,
    check_span,
    external_api_span,
    get_tracer,
    http_span,
    init_tracing,
    init_tracing_from_env,
    is_tracing_enabled,
    record_span_exception,
    set_span_attribute,
    traced_check,
    traced_http,
)


def test_init_tracing_console():
    """Test initializing tracing with console export."""
    tracer = init_tracing(
        service_name="test-service",
        console_export=True,
    )
    assert tracer is not None
    assert is_tracing_enabled()
    assert get_tracer() is tracer


def test_init_tracing_idempotent():
    """Test that re-initialization returns same tracer."""
    tracer1 = init_tracing(service_name="test", console_export=True)
    tracer2 = init_tracing(service_name="test", console_export=True)
    assert tracer1 is tracer2


def test_init_tracing_from_env_disabled():
    """Test that tracing from env returns None when disabled."""
    with patch.dict(os.environ, {"WA_TRACING_ENABLED": "false"}):
        tracer = init_tracing_from_env()
        assert tracer is None


def test_init_tracing_from_env_enabled():
    """Test that tracing from env works when enabled."""
    with patch.dict(os.environ, {
        "WA_TRACING_ENABLED": "true",
        "WA_TRACING_SERVICE_NAME": "env-test",
        "WA_TRACING_CONSOLE_EXPORT": "true",
    }):
        tracer = init_tracing_from_env()
        assert tracer is not None
        assert is_tracing_enabled()


def test_audit_span():
    """Test audit span context manager."""
    init_tracing(console_export=True)

    with audit_span("run-123", "https://example.com", "default") as span:
        assert span is not None
        span.set_attribute("test.attr", "value")


def test_audit_span_with_attributes():
    """Test audit span with custom attributes."""
    init_tracing(console_export=True)

    attrs = {"custom": "value", "count": 5}
    with audit_span("run-123", "https://example.com", "default", attributes=attrs) as span:
        assert span is not None


def test_check_span():
    """Test check span context manager."""
    init_tracing(console_export=True)

    with check_span("page", "run-123", "https://example.com") as span:
        assert span is not None
        span.set_attribute("check.phase", "analysis")


def test_check_span_with_attributes():
    """Test check span with custom attributes."""
    init_tracing(console_export=True)

    attrs = {"custom": "value"}
    with check_span("schema", "run-123", "https://example.com", attributes=attrs) as span:
        assert span is not None


def test_http_span():
    """Test HTTP span context manager."""
    init_tracing(console_export=True)

    with http_span("GET", "https://example.com/page", "example.com") as span:
        assert span is not None


def test_http_span_with_attributes():
    """Test HTTP span with custom attributes."""
    init_tracing(console_export=True)

    attrs = {"custom": "value"}
    with http_span("POST", "https://example.com/api", "example.com", attributes=attrs) as span:
        assert span is not None


def test_external_api_span():
    """Test external API span context manager."""
    init_tracing(console_export=True)

    with external_api_span("pagespeed", {"version": "v5"}) as span:
        assert span is not None


def test_add_span_event():
    """Test adding events to span."""
    init_tracing(console_export=True)

    with audit_span("run-123", "https://example.com", "default") as span:
        add_span_event(span, "test_event", {"key": "value"})


def test_set_span_attribute():
    """Test setting span attribute."""
    init_tracing(console_export=True)

    with audit_span("run-123", "https://example.com", "default") as span:
        set_span_attribute(span, "test.key", "test_value")


def test_record_span_exception():
    """Test recording exception on span."""
    init_tracing(console_export=True)

    with audit_span("run-123", "https://example.com", "default") as span:
        try:
            raise ValueError("test error")
        except ValueError as e:
            record_span_exception(span, e)


def test_traced_check_decorator():
    """Test traced_check decorator."""
    init_tracing(console_export=True)

    @traced_check("test_check")
    def my_check(run_id="run-123", url="https://example.com"):
        return [], {"evidence": "data"}

    result = my_check(run_id="run-123", url="https://example.com")
    assert result == ([], {"evidence": "data"})


def test_traced_check_decorator_with_findings():
    """Test traced_check decorator with findings result."""
    init_tracing(console_export=True)

    @traced_check("test_check")
    def my_check(run_id="run-123", url="https://example.com"):
        return [{"severity": "high"}], {"evidence": "data"}

    result = my_check(run_id="run-123", url="https://example.com")
    assert len(result[0]) == 1


def test_traced_http_decorator():
    """Test traced_http decorator."""
    init_tracing(console_export=True)

    class MockResponse:
        status_code = 200

    @traced_http
    def my_http(url, method="GET"):
        return MockResponse()

    result = my_http("https://example.com")
    assert result.status_code == 200


def test_traced_audit_context():
    """Test TracedAuditContext."""
    init_tracing(console_export=True)

    with TracedAuditContext("run-123", "https://example.com", "default") as ctx:
        assert ctx.span is not None

        check_span = ctx.start_check("page")
        assert check_span is not None

        ctx.end_check("page", status="ok", findings_count=2)

        ctx.add_event("custom_event", {"data": "value"})


def test_traced_audit_context_with_error():
    """Test TracedAuditContext with error."""
    init_tracing(console_export=True)

    try:
        with TracedAuditContext("run-123", "https://example.com", "default") as ctx:
            ctx.start_check("page")
            raise ValueError("test error")
    except ValueError:
        pass  # Expected


def test_helpers_with_none_span():
    """Test helper functions handle None span gracefully."""
    add_span_event(None, "event")
    set_span_attribute(None, "key", "value")
    record_span_exception(None, ValueError("test"))

    # Should not raise


def test_console_export_only():
    """Test that console export works without OTLP endpoint."""
    tracer = init_tracing(
        service_name="console-only",
        console_export=True,
    )
    assert tracer is not None


def test_get_tracer_auto_init():
    """Test get_tracer auto-initializes if not initialized."""
    # Reset global state
    import auditor_toolkit.tracing as tracing_module
    tracing_module._tracer = None
    tracing_module._tracing_initialized = False

    tracer = get_tracer()
    assert tracer is not None
    assert is_tracing_enabled()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
