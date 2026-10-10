#!/usr/bin/env python3
"""Stdlib-only local search provider boundary for Money Machine discovery.

SearXNG is accepted only over loopback HTTP. Expected provider failures are
returned as typed states rather than raised into the operator or supervisor.
Search results are normalized to public discovery hints only; this layer has no
contact, approval, pricing, model, or outreach authority.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

import mm_core as core

MAX_RESPONSE = 2 * 1024 * 1024
DEFAULT_TIMEOUT = 20
USER_AGENT = "WEBSITE-AUDITOR-Discovery/1.0"

OK = "OK"
BLOCKED_ENDPOINT_INVALID = "BLOCKED_ENDPOINT_INVALID"
BLOCKED_NOT_LOOPBACK = "BLOCKED_NOT_LOOPBACK"
BLOCKED_NOT_LISTENING = "BLOCKED_NOT_LISTENING"
BLOCKED_TIMEOUT = "BLOCKED_TIMEOUT"
BLOCKED_HTTP_STATUS = "BLOCKED_HTTP_STATUS"
BLOCKED_NOT_JSON = "BLOCKED_NOT_JSON"
BLOCKED_TOO_LARGE = "BLOCKED_TOO_LARGE"
BLOCKED_INVALID_JSON = "BLOCKED_INVALID_JSON"
BLOCKED_CIRCUIT_OPEN = "BLOCKED_CIRCUIT_OPEN"

REMEDY = {
    BLOCKED_ENDPOINT_INVALID: "Use a valid loopback HTTP endpoint.",
    BLOCKED_NOT_LOOPBACK: "Discovery accepts only http://127.0.0.1, http://localhost, or http://[::1].",
    BLOCKED_NOT_LISTENING: "Start the local SearXNG service and retry.",
    BLOCKED_TIMEOUT: "Inspect the local SearXNG service and retry after it is responsive.",
    BLOCKED_HTTP_STATUS: "Inspect the local SearXNG service logs and JSON API configuration.",
    BLOCKED_NOT_JSON: "Enable JSON output in SearXNG: search.formats must include json.",
    BLOCKED_TOO_LARGE: "Reduce the query/result limit; the provider response exceeded the safety cap.",
    BLOCKED_INVALID_JSON: "SearXNG returned JSON without the required results array.",
    BLOCKED_CIRCUIT_OPEN: "The local search breaker is cooling down after repeated failures.",
}


def _endpoint(endpoint):
    raw = str(endpoint or "").strip()
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid SearXNG endpoint") from exc
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "http":
        raise ValueError("SearXNG endpoint must use loopback HTTP")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("SearXNG endpoint must be loopback HTTP")
    if parsed.username or parsed.password:
        raise ValueError("SearXNG endpoint credentials are not allowed")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("invalid SearXNG port")
    return raw.rstrip("/"), (port or 80)


def _request(endpoint, params, timeout):
    url = endpoint + "/search?" + urlencode(params)
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as response:
            body = response.read(MAX_RESPONSE + 1)
    except HTTPError as exc:
        return BLOCKED_HTTP_STATUS, "HTTP " + str(exc.code)
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, TimeoutError):
            return BLOCKED_TIMEOUT, "timeout"
        if isinstance(reason, ConnectionRefusedError):
            return BLOCKED_NOT_LISTENING, "connection refused"
        return BLOCKED_NOT_LISTENING, type(reason).__name__ + ": " + str(reason)
    except TimeoutError:
        return BLOCKED_TIMEOUT, "timeout"
    except OSError as exc:
        return BLOCKED_NOT_LISTENING, type(exc).__name__ + ": " + str(exc)

    if len(body) > MAX_RESPONSE:
        return BLOCKED_TOO_LARGE, "response size limit exceeded"
    try:
        document = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return BLOCKED_NOT_JSON, "response was not JSON"
    if not isinstance(document, dict) or not isinstance(document.get("results"), list):
        return BLOCKED_INVALID_JSON, "missing results[]"
    return OK, document


def probe(endpoint="http://127.0.0.1:8888", timeout=5):
    try:
        endpoint, port = _endpoint(endpoint)
    except ValueError as exc:
        return {
            "provider": "searxng",
            "endpoint": str(endpoint or ""),
            "state": BLOCKED_ENDPOINT_INVALID,
            "ok": False,
            "reason": str(exc),
            "remedy": REMEDY[BLOCKED_ENDPOINT_INVALID],
            "checked_at": core.now(),
        }

    state, payload = _request(
        endpoint,
        {"q": "localhost", "format": "json", "categories": "general", "safesearch": "1"},
        timeout,
    )
    result = {
        "provider": "searxng",
        "endpoint": endpoint,
        "port": port,
        "state": state,
        "ok": state == OK,
        "json_api_enabled": state not in {BLOCKED_NOT_JSON, BLOCKED_INVALID_JSON},
        "checked_at": core.now(),
        "scope": "Reachability and JSON capability only; not a result-quality claim.",
    }
    if state == OK:
        result["result_count"] = len(payload["results"])
    else:
        result["reason"] = payload
        result["remedy"] = REMEDY.get(state, "Inspect the local SearXNG service.")
    return result


def _state_dir():
    path = Path(core.root()) / "state"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cache_dir():
    path = _state_dir() / "search-cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _breaker_path():
    return _state_dir() / "search-breaker.json"


def cache_key(endpoint, query, region, params):
    raw = json.dumps([endpoint, query, region, params], sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def cache_read(key, ttl_hours):
    path = _cache_dir() / (key + ".json")
    if not path.is_file() or ttl_hours <= 0:
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        cached_at = float(document.get("cached_at", 0))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if time.time() - cached_at > ttl_hours * 3600:
        return None
    payload = document.get("payload")
    return payload if isinstance(payload, dict) else None


def cache_write(key, payload):
    path = _cache_dir() / (key + ".json")
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps({"cached_at": time.time(), "payload": payload}, sort_keys=True),
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


def _breaker_read():
    try:
        data = json.loads(_breaker_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {"failures": 0, "opened_at": None}
    return data if isinstance(data, dict) else {"failures": 0, "opened_at": None}


def _breaker_write(data):
    path = _breaker_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _breaker_open():
    state = _breaker_read()
    threshold = max(1, int(os.environ.get("MM_SEARCH_BREAKER_FAILS", "3")))
    cooldown = max(1, int(os.environ.get("MM_SEARCH_BREAKER_COOLDOWN", "300")))
    if int(state.get("failures") or 0) < threshold:
        return False
    opened_at = float(state.get("opened_at") or 0)
    if time.time() - opened_at >= cooldown:
        return False
    return True


def _record_failure():
    state = _breaker_read()
    failures = int(state.get("failures") or 0) + 1
    threshold = max(1, int(os.environ.get("MM_SEARCH_BREAKER_FAILS", "3")))
    state = {
        "failures": failures,
        "opened_at": time.time() if failures >= threshold else state.get("opened_at"),
    }
    _breaker_write(state)


def _record_success():
    _breaker_write({"failures": 0, "opened_at": None})


def _normalize_results(document, limit):
    out = []
    for item in document.get("results", [])[: max(1, min(int(limit), 50))]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        engines = item.get("engines")
        if not isinstance(engines, list):
            engines = [item.get("engine")] if item.get("engine") else []
        try:
            score = float(item.get("score") or 0)
        except (TypeError, ValueError):
            score = 0.0
        out.append(
            {
                "title": str(item.get("title") or "")[:500],
                "url": url[:2000],
                "content": str(item.get("content") or "")[:4000],
                "engines": [str(x)[:80] for x in engines if x][:12],
                "score": score,
            }
        )
    return out


def search(
    query,
    region,
    endpoint="http://127.0.0.1:8888",
    limit=20,
    timeout=DEFAULT_TIMEOUT,
    cache_hours=None,
    use_network=True,
):
    endpoint, _ = _endpoint(endpoint)
    query = str(query or "").strip()
    region = str(region or "").strip()
    if not query:
        raise ValueError("query is required")
    if not region:
        raise ValueError("region is required")
    limit = max(1, min(int(limit), 50))
    ttl = int(os.environ.get("MM_SEARCH_CACHE_HOURS", "24")) if cache_hours is None else int(cache_hours)
    params = {
        "q": (query + " " + region).strip(),
        "format": "json",
        "categories": "general",
        "safesearch": "1",
        "language": "en",
    }
    key = cache_key(endpoint, query, region, {"limit": limit, **params})
    query_ref = hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]

    cached = cache_read(key, ttl)
    if cached is not None:
        return {
            "state": OK,
            "provider": "searxng",
            "endpoint": endpoint,
            "query_ref": query_ref,
            "cache": "hit",
            "results": list(cached.get("results") or [])[:limit],
        }

    if not use_network:
        return {
            "state": BLOCKED_NOT_LISTENING,
            "provider": "searxng",
            "endpoint": endpoint,
            "query_ref": query_ref,
            "cache": "miss",
            "results": [],
            "reason": "network disabled and no valid cached result exists",
            "remedy": "Run once with the local SearXNG service available to populate the cache.",
        }

    if _breaker_open():
        return {
            "state": BLOCKED_CIRCUIT_OPEN,
            "provider": "searxng",
            "endpoint": endpoint,
            "query_ref": query_ref,
            "cache": "miss",
            "results": [],
            "remedy": REMEDY[BLOCKED_CIRCUIT_OPEN],
        }

    state, payload = _request(endpoint, params, timeout)
    if state != OK:
        _record_failure()
        return {
            "state": state,
            "provider": "searxng",
            "endpoint": endpoint,
            "query_ref": query_ref,
            "cache": "miss",
            "results": [],
            "reason": payload,
            "remedy": REMEDY.get(state, "Inspect the local SearXNG service."),
        }

    _record_success()
    normalized = _normalize_results(payload, limit)
    cached_payload = {"results": normalized}
    if ttl > 0:
        cache_write(key, cached_payload)
    return {
        "state": OK,
        "provider": "searxng",
        "endpoint": endpoint,
        "query_ref": query_ref,
        "cache": "miss",
        "results": normalized,
    }
