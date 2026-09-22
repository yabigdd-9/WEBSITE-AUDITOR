"""Lightweight P3 runtime guards.

Disk exhaustion pauses new supervisor work. Network degradation is observable but does
not stop deterministic/local stages; network-dependent workers already retry/defer.

P3 hardening: the network guard is a multi-probe check (env-overridable via
MM_NETWORK_PROBE_HOSTS, comma-separated host:port entries tried in order) whose
result is cached on disk for PROBE_TTL_SECONDS. Degraded-state log rows are
deduplicated (at most one per TTL window, and at most one per LOG_DEDUP_SECONDS
while continuously degraded) so a sandboxed/offline host cannot flood errors.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import time
from pathlib import Path

import mm_core as core

PROBE_TTL_SECONDS = int(os.environ.get("MM_NETWORK_PROBE_TTL", "60"))
LOG_DEDUP_SECONDS = int(os.environ.get("MM_NETWORK_LOG_DEDUP", "3600"))
DEFAULT_PROBE_HOSTS = "example.com:443"


def disk_guard(root=None, min_free_mb=None):
    root = Path(root or core.root())
    minimum = int(min_free_mb if min_free_mb is not None else os.environ.get("MM_MIN_FREE_MB", "1024"))
    usage = shutil.disk_usage(root)
    free_mb = usage.free // (1024 * 1024)
    return {
        "ok": free_mb >= minimum,
        "free_mb": free_mb,
        "minimum_free_mb": minimum,
        "action": "continue" if free_mb >= minimum else "pause_new_work",
    }


def _parse_probe_hosts(hosts=None, host=None, port=443):
    """Resolve the ordered probe list of (host, port) tuples.

    Priority: explicit `hosts` > legacy explicit `host` > MM_NETWORK_PROBE_HOSTS
    (comma-separated host[:port]) > legacy MM_NETWORK_PROBE_HOST > default.
    """
    if hosts:
        raw = list(hosts)
    elif host:
        raw = ["%s:%s" % (host, port)]
    else:
        env = os.environ.get("MM_NETWORK_PROBE_HOSTS")
        if env:
            raw = [part.strip() for part in env.split(",") if part.strip()]
        else:
            legacy = os.environ.get("MM_NETWORK_PROBE_HOST")
            raw = ["%s:%s" % (legacy, port)] if legacy else [DEFAULT_PROBE_HOSTS]
    parsed = []
    for entry in raw:
        if isinstance(entry, (tuple, list)):
            parsed.append((str(entry[0]), int(entry[1])))
            continue
        text = str(entry)
        if ":" in text:
            h, _, p = text.rpartition(":")
            parsed.append((h, int(p)))
        else:
            parsed.append((text, 443))
    return parsed


def _probe_once(host, port, timeout, resolver=None, connector=None):
    """Attempt DNS + TCP connect to one host. Returns None on success, error str."""
    resolver = resolver or socket.getaddrinfo
    try:
        addresses = resolver(host, port, type=socket.SOCK_STREAM)
        if not addresses:
            raise OSError("no addresses")
        family, socktype, proto, _, sockaddr = addresses[0]
        if connector is not None:
            connector(family, socktype, proto, sockaddr, timeout)
        else:
            with socket.socket(family, socktype, proto) as sock:
                sock.settimeout(timeout)
                sock.connect(sockaddr)
        return None
    except OSError as exc:
        return "%s: %s" % (type(exc).__name__, str(exc)[:200])


def _cache_path(cache_path=None):
    return Path(cache_path) if cache_path else core.root() / "state" / "network_guard.json"


def _read_cache(cache_path=None):
    try:
        return json.loads(_cache_path(cache_path).read_text())
    except Exception:
        return None


def _write_cache(state, cache_path=None):
    path = _cache_path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, sort_keys=True, default=str))
    os.replace(tmp, path)


def network_guard(host=None, port=443, timeout=2.0, resolver=None, hosts=None,
                  connector=None, use_cache=True, cache_path=None):
    """Multi-probe public DNS/TCP reachability check; never a provider health claim.

    Probes are tried in order; success if ANY responds. Results are cached on
    disk for PROBE_TTL_SECONDS so repeated callers within a window share one
    probe outcome (cached results are flagged with "cached": true). Injected
    resolver/connector (tests) bypass the cache entirely.
    """
    if use_cache and resolver is None and connector is None:
        cached = _read_cache(cache_path)
        if cached and cached.get("checked_at"):
            try:
                age = time.time() - float(cached.get("checked_at_epoch", 0))
            except (TypeError, ValueError):
                age = PROBE_TTL_SECONDS + 1
            if 0 <= age < PROBE_TTL_SECONDS:
                return {**cached["result"], "cached": True,
                        "checked_at": cached["checked_at"]}

    attempts = []
    winner = None
    last_error = None
    for probe_host, probe_port in _parse_probe_hosts(hosts, host, port):
        error = _probe_once(probe_host, probe_port, timeout, resolver, connector)
        attempts.append({"host": probe_host, "port": probe_port,
                         "ok": error is None,
                         **({"error": error} if error else {})})
        if error is None:
            winner = (probe_host, probe_port)
            break
        last_error = error

    ok = winner is not None
    result = {
        "ok": ok,
        "host": winner[0] if winner else attempts[-1]["host"] if attempts else None,
        "port": winner[1] if winner else attempts[-1]["port"] if attempts else None,
        "scope": "basic DNS/TCP reachability only",
        "attempts": attempts,
        "cached": False,
        "checked_at": core.now(),
        "action": ("network_workers_may_run" if ok
                   else "network_workers_defer_or_retry; local work may continue"),
    }
    if not ok and last_error:
        result["error"] = last_error

    if use_cache and resolver is None and connector is None:
        previous = _read_cache(cache_path) or {}
        prev_ok = (previous.get("result") or {}).get("ok")
        since = previous.get("since")
        if prev_ok != ok or not since:
            since = result["checked_at"]
        _write_cache({
            "checked_at": result["checked_at"],
            "checked_at_epoch": time.time(),
            "ok": ok,
            "since": since,
            "result": result,
            "last_logged_degraded_at": previous.get("last_logged_degraded_at"),
            "last_logged_degraded_epoch": previous.get("last_logged_degraded_epoch"),
        }, cache_path)
    return result


def network_guard_event(cache_path=None, timeout=2.0):
    """Probe (with cache) and decide whether a log row is warranted.

    Returns (result, log_kind) where log_kind is one of:
      * "network_degraded" — fresh failure, at most one per TTL window AND at
        most one per LOG_DEDUP_SECONDS while continuously degraded
      * "network_recovered" — state flipped degraded -> ok
      * None — nothing new worth logging
    """
    prior = _read_cache(cache_path) or {}
    prior_ok = (prior.get("result") or {}).get("ok")
    result = network_guard(timeout=timeout, use_cache=True, cache_path=cache_path)
    if result.get("cached"):
        return result, None  # TTL window: never log from a cached observation
    if result["ok"]:
        if prior_ok is False:
            return result, "network_recovered"
        return result, None
    last_logged = prior.get("last_logged_degraded_epoch") or 0
    if time.time() - float(last_logged) < LOG_DEDUP_SECONDS:
        return result, None
    state = _read_cache(cache_path) or {}
    state["last_logged_degraded_at"] = result["checked_at"]
    state["last_logged_degraded_epoch"] = time.time()
    _write_cache(state, cache_path)
    return result, "network_degraded"


def network_status(cache_path=None):
    """Read-only degraded-mode view for health surfaces; never opens a socket."""
    cached = _read_cache(cache_path)
    if not cached or "ok" not in cached:
        return {"mode": "unknown", "since": None, "checked_at": None,
                "source": "no probe recorded yet"}
    return {
        "mode": "ok" if cached["ok"] else "degraded",
        "since": cached.get("since"),
        "checked_at": cached.get("checked_at"),
        "probe_ttl_seconds": PROBE_TTL_SECONDS,
    }


def snapshot(root=None, probe_network=True):
    return {
        "checked_at": core.now(),
        "disk": disk_guard(root),
        "network": network_guard() if probe_network else {
            "ok": None,
            "scope": "not probed",
            "action": "unknown",
        },
        "paid_calls": 0,
        "external_sends": 0,
    }
