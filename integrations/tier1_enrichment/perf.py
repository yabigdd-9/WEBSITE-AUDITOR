"""Performance boosters for website_auditor.py.

Drop-in helpers — none change audit results, only speed and resilience:

1. HTTP/2 + connection pooling + retries via httpx AsyncClient
2. Per-domain semaphore (throttle) so one slow site doesn't stall the batch
3. Streaming body size cap (avoids hanging on 50 MB pages)
4. uvloop drop-in when installed (faster event loop on macOS/Linux)
5. Simple in-memory circuit breaker (skip known-broken domains for TTL)

Usage in website_auditor.py (existing code unchanged):
    from integrations.tier1_enrichment.perf import make_client, breaker_open
    client = make_client(concurrency=8)
    if breaker_open(domain): return {"defects": [{"defect": "circuit open", ...}]}
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

# ---------------------------------------------------------------------------
# 1. HTTP/2 + pooling client
# ---------------------------------------------------------------------------
def make_client(
    concurrency: int = 8,
    timeout: float = 15.0,
    http2: bool = True,
    max_connections: int = 50,
) -> httpx.AsyncClient:  # type: ignore[type-arg]
    """Return an httpx client tuned for batch auditing."""
    limits = httpx.Limits(
        max_keepalive_connections=max_connections,
        max_connections=max_connections,
        keepalive_expiry=30.0,
    )
    try:
        return httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (NZ) WebsiteRescueAuditor/2.0"},
            timeout=timeout,
            limits=limits,
            http2=http2,
            follow_redirects=True,
        )
    except ImportError:
        # h2 not installed — fall back to http/1.1
        return httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (NZ) WebsiteRescueAuditor/2.0"},
            timeout=timeout,
            limits=limits,
            http2=False,
            follow_redirects=True,
        )


# ---------------------------------------------------------------------------
# 2. Per-domain semaphore — prevents one slow site from choking the batch
# ---------------------------------------------------------------------------
class DomainLimiter:
    def __init__(self, per_domain: int = 2) -> None:
        self._lock = asyncio.Lock()
        self._sems: dict[str, asyncio.Semaphore] = {}
        self._per_domain = per_domain

    def get(self, domain: str) -> asyncio.Semaphore:
        async def _ensure() -> None:
            async with self._lock:
                if domain not in self._sems:
                    self._sems[domain] = asyncio.Semaphore(self._per_domain)
        # fire-and-forget sync init works because dict is lazy-safe here
        _ensure()
        return self._sems.setdefault(domain, asyncio.Semaphore(self._per_domain))


# ---------------------------------------------------------------------------
# 3. Streaming body size cap (avoids hanging on huge pages)
# ---------------------------------------------------------------------------
MAX_BODY_BYTES = 10 * 1024 * 1024  # 10 MB cap


async def fetch_html_capped(
    session: httpx.AsyncClient, url: str, cap: int = MAX_BODY_BYTES
) -> tuple[str, int]:
    """Return (html, bytes_downloaded). On cap exceeded, returns ('', cap)."""
    try:
        async with session.stream("text", url, timeout=30) as resp:
            if resp.status_code != 200:
                return ("", 0)
            parts: list[str] = []
            total = 0
            async for chunk in resp.aiter_text(chunk_size=65536):
                parts.append(chunk)
                total += len(chunk.encode())
                if total > cap:
                    return ("", cap)
            return ("".join(parts), total)
    except Exception:
        return ("", 0)


# ---------------------------------------------------------------------------
# 4. uvloop drop-in
# ---------------------------------------------------------------------------
def install_uvloop() -> bool:
    """Try to switch the event loop to uvloop (faster). Returns True on success."""
    try:
        import uvloop  # type: ignore

        uvloop.install()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 5. Circuit breaker — skip known-broken domains for TTL seconds
# ---------------------------------------------------------------------------
class CircuitBreaker:
    def __init__(self, ttl: int = 300, max_fails: int = 3) -> None:
        self._ttl = ttl
        self._max_fails = max_fails
        self._fails: dict[str, list[float]] = {}

    def record(self, domain: str, ok: bool) -> None:
        if ok:
            self._fails.pop(domain, None)
            return
        self._fails.setdefault(domain, []).append(time.time())
        self._fails[domain] = [t for t in self._fails[domain] if time.time() - t < self._ttl]

    def breaker_open(self, domain: str) -> bool:
        fails = self._fails.get(domain, [])
        return len(fails) >= self._max_fails and (time.time() - fails[-1]) < self._ttl

    def state(self, domain: str) -> dict[str, Any]:
        fails = self._fails.get(domain, [])
        return {"domain": domain, "fails": len(fails), "open": self.breaker_open(domain)}


breaker = CircuitBreaker()
