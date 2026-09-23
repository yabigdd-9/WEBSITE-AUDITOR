"""Tests for runtime recovery and retry policies."""

from auditor_toolkit.runtime.recovery import (
    classify_error,
    get_retry_policy,
    should_retry,
    RetryPolicy,
)


def test_classify_http_429():
    assert classify_error(Exception("rate limit"), status_code=429) == "HTTP_429"


def test_classify_http_5xx():
    assert classify_error(Exception("server error"), status_code=500) == "HTTP_5XX"


def test_classify_browser_crash():
    assert classify_error(Exception("browser crashed")) == "BROWSER_CRASH"


def test_classify_timeout():
    assert classify_error(Exception("request timed out")) == "TIMEOUT"


def test_classify_transient():
    assert classify_error(Exception("connection refused")) == "TRANSIENT_NETWORK"


def test_classify_permanent_4xx():
    assert classify_error(Exception("not found"), status_code=404) == "PERMANENT_4XX"


def test_retry_policy_429():
    policy = get_retry_policy("HTTP_429")
    assert policy.respect_retry_after
    assert policy.retries == 4


def test_retry_policy_browser_crash():
    policy = get_retry_policy("BROWSER_CRASH")
    assert policy.recycle_worker
    assert policy.retries == 1


def test_retry_policy_permanent():
    policy = get_retry_policy("PERMANENT_4XX")
    assert policy.retries == 0


def test_should_retry_true():
    assert should_retry("TRANSIENT_NETWORK", 1)


def test_should_retry_false():
    assert not should_retry("PERMANENT_4XX", 1)


def test_should_retry_exhausted():
    assert not should_retry("HTTP_429", 5)  # max 4 retries
