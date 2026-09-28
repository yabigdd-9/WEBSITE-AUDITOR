#!/usr/bin/env python3
"""SearXNG client bridge for local discovery pipeline.

This module is a thin bridge that re-exports the existing deterministic
discovery functions from mm_discovery.py, ensuring the local SearXNG
endpoint (127.0.0.1:8888) is the single source of truth for candidate
generation.  No external sends, no model calls, no paid services.

All functions delegate to mm_discovery, which already enforces:
  * Loopback-only endpoint validation (SSRF-safe)
  * SearchBlocked typed failures for unreachable/invalid responses
  * Deduplication by canonical_host
  * URL normalization and private-IP rejection
"""

from __future__ import annotations

import json
from urllib.request import urlopen, Request
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.error import HTTPError, URLError

# Re-export from mm_discovery to avoid duplication of SSRF/validation logic
from mm_discovery import (
    SearchBlocked,
    searxng_candidates as _searxng_candidates,
    MAX_SEARCH_RESULTS,
    MAX_SEARCH_RESPONSE,
    SEARCH_TIMEOUT,
    USER_AGENT,
)

EXTERNAL_SENDS = 0  # invariant: this module never sends externally


def query(query_text: str, region: str,
          endpoint: str = "http://127.0.0.1:8888",
          limit: int = 20) -> list[dict]:
    """Query local SearXNG and return deduplicated candidate dicts.

    Returns list of dicts: {canonical_host, name, region, public_website,
    source, canonical_host}

    Raises SearchBlocked (BLOCKED_SEARCH_*) when the endpoint is unreachable
    or returns malformed data.  No external sends are recorded.
    """
    return _searxng_candidates(query_text, region, endpoint, limit)


def status(endpoint: str = "http://127.0.0.1:8888") -> dict:
    """Check whether the local SearXNG service is reachable."""
    from urllib.request import urlopen
    import time as _time

    params = urlencode({"q": "healthcheck", "format": "json"})
    url = endpoint.rstrip("/") + "/search?" + params
    t0 = _time.monotonic()
    try:
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urlopen(request, timeout=SEARCH_TIMEOUT) as response:
            response.read(MAX_SEARCH_RESPONSE + 1)
        return {
            "endpoint": endpoint,
            "reachable": True,
            "external_sends": EXTERNAL_SENDS,
            "latency_ms": round((_time.monotonic() - t0) * 1000, 1),
        }
    except Exception as exc:
        code = getattr(exc, "code", None)
        reason = str(exc)
        if isinstance(exc, URLError):
            code = "BLOCKED_SEARCH_SERVICE_ABSENT"
        return {
            "endpoint": endpoint,
            "reachable": False,
            "error_code": code,
            "error_detail": reason,
            "external_sends": EXTERNAL_SENDS,
            "latency_ms": round((_time.monotonic() - t0) * 1000, 1),
        }
