"""Lightweight P3 runtime guards.

Disk exhaustion pauses new supervisor work. Network degradation is observable but does
not stop deterministic/local stages; network-dependent workers already retry/defer.
"""
from __future__ import annotations

import os
import shutil
import socket
from pathlib import Path

import mm_core as core


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


def network_guard(host=None, port=443, timeout=2.0, resolver=None):
    """Check basic public DNS/TCP reachability; never a provider health claim."""
    host = host or os.environ.get("MM_NETWORK_PROBE_HOST", "example.com")
    resolver = resolver or socket.getaddrinfo
    try:
        addresses = resolver(host, port, type=socket.SOCK_STREAM)
        if not addresses:
            raise OSError("no addresses")
        family, socktype, proto, _, sockaddr = addresses[0]
        with socket.socket(family, socktype, proto) as sock:
            sock.settimeout(timeout)
            sock.connect(sockaddr)
        return {
            "ok": True,
            "host": host,
            "port": port,
            "scope": "basic DNS/TCP reachability only",
            "action": "network_workers_may_run",
        }
    except OSError as exc:
        return {
            "ok": False,
            "host": host,
            "port": port,
            "scope": "basic DNS/TCP reachability only",
            "error": f"{type(exc).__name__}: {str(exc)[:200]}",
            "action": "network_workers_defer_or_retry; local work may continue",
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
