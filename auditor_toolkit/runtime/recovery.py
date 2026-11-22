"""Recovery, retry classification, and retry policies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RetryClass = Literal[
    "TRANSIENT_NETWORK", "DNS_TEMPORARY", "HTTP_429", "HTTP_5XX",
    "BROWSER_CRASH", "TOOL_CRASH", "DATABASE_TEMPORARY", "TIMEOUT",
    "PERMANENT_4XX", "INVALID_TARGET", "POLICY_BLOCKED",
    "PARSER_BUG", "POISON_JOB", "CORRUPT_ARTIFACT",
]


@dataclass(frozen=True)
class RetryPolicy:
    retries: int = 0
    exponential_backoff: bool = False
    jitter: bool = False
    respect_retry_after: bool = False
    recycle_worker: bool = False
    quarantine: bool = False


_RETRY_POLICIES: dict[RetryClass, RetryPolicy] = {
    "TRANSIENT_NETWORK": RetryPolicy(retries=4, exponential_backoff=True, jitter=True),
    "DNS_TEMPORARY": RetryPolicy(retries=3, exponential_backoff=True),
    "HTTP_429": RetryPolicy(retries=4, respect_retry_after=True),
    "HTTP_5XX": RetryPolicy(retries=3, exponential_backoff=True),
    "BROWSER_CRASH": RetryPolicy(retries=1, recycle_worker=True),
    "TOOL_CRASH": RetryPolicy(retries=1),
    "DATABASE_TEMPORARY": RetryPolicy(retries=5, exponential_backoff=True),
    "TIMEOUT": RetryPolicy(retries=2, exponential_backoff=True),
    "PERMANENT_4XX": RetryPolicy(retries=0),
    "INVALID_TARGET": RetryPolicy(retries=0),
    "POLICY_BLOCKED": RetryPolicy(retries=0),
    "PARSER_BUG": RetryPolicy(retries=0, quarantine=True),
    "POISON_JOB": RetryPolicy(retries=0, quarantine=True),
    "CORRUPT_ARTIFACT": RetryPolicy(retries=0, quarantine=True),
}


def classify_error(error: Exception, status_code: int | None = None) -> RetryClass:
    """Classify an error into a retry class."""
    if status_code == 429:
        return "HTTP_429"
    if status_code and 500 <= status_code < 600:
        return "HTTP_5XX"
    if status_code and 400 <= status_code < 500:
        return "PERMANENT_4XX"
    err_str = str(error).lower()
    if "browser" in err_str or "playwright" in err_str or "chromium" in err_str:
        return "BROWSER_CRASH"
    if "timeout" in err_str or "timed out" in err_str:
        return "TIMEOUT"
    if "dns" in err_str or "name resolution" in err_str:
        return "DNS_TEMPORARY"
    if "connection" in err_str or "network" in err_str:
        return "TRANSIENT_NETWORK"
    if "database" in err_str or "sqlite" in err_str:
        return "DATABASE_TEMPORARY"
    return "TOOL_CRASH"


def get_retry_policy(error_class: RetryClass) -> RetryPolicy:
    return _RETRY_POLICIES.get(error_class, RetryPolicy(retries=0, quarantine=True))


def should_retry(error_class: RetryClass, attempt: int) -> bool:
    policy = get_retry_policy(error_class)
    return attempt <= policy.retries
