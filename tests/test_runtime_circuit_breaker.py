"""Tests for runtime circuit breakers."""

import time

from auditor_toolkit.runtime.circuit_breaker import CircuitBreaker, CircuitBreakerRegistry


def test_circuit_breaker_closed():
    cb = CircuitBreaker(name="test", threshold=3)
    assert cb.can_execute()
    assert cb.state == "CLOSED"


def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker(name="test", threshold=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "OPEN"
    assert not cb.can_execute()


def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker(name="test2", threshold=2, cooldown_seconds=1)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "OPEN"
    assert not cb.can_execute()


def test_circuit_breaker_closes_on_success():
    cb = CircuitBreaker(name="test", threshold=2)
    cb.record_failure()
    cb.record_success()
    assert cb.failure_count == 0
    assert cb.state == "CLOSED"


def test_registry():
    cb = CircuitBreakerRegistry.get("domain:example.com", threshold=5)
    assert cb.name == "domain:example.com"
    CircuitBreakerRegistry.record_success("domain:example.com")
    assert CircuitBreakerRegistry.can_execute("domain:example.com")
