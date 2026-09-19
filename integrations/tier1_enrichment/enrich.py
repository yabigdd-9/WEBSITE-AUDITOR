"""Orchestrator: run enrichment and merge it into an audit dict.

Contract (additive only — existing keys are never modified):
- input:  audit dict from ``website_auditor.audit_one`` (needs ``url`` +
  response headers; headers may be passed explicitly)
- output: same dict + ``audit["enrichment"]`` with per-source results
- grading defects from the local header grader are appended to
  ``audit["defects"]`` using the auditor's own ``{defect, impact}`` shape,
  so ``score_defects`` keeps working unchanged.

Every source fails closed to ``{"status": "skipped", ...}`` — enrichment can
never break an audit.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any

from integrations.tier1_enrichment.cache import EnrichmentCache
from integrations.tier1_enrichment.graders import grade_security_headers
from integrations.tier1_enrichment.sources import (
    check_pagespeed,
    check_ranknibbler,
    check_ssllabs,
    check_urlscan_search,
    check_w3c,
)


def _run_coro(coro):
    """Run a coroutine from sync OR async callers.

    ``asyncio.run()`` raises inside a running loop (the auditor calls us from
    one), so: reuse the running loop when there is one, else ``asyncio.run``.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _client(headers: dict | None = None):
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("httpx is required (see requirements.txt)") from exc
    return httpx.AsyncClient(headers=headers or {})


async def enrich_async(url: str, headers: dict | None = None,
         cache: EnrichmentCache | None = None,
         include: tuple[str, ...] = ("headers", "w3c", "ssllabs", "urlscan"),
         ) -> dict:
    """Run the keyless source set concurrently. Keyed sources are opt-in via
    ``include`` (``"pagespeed"``, ``"ranknibbler"``)."""
    cache = cache or EnrichmentCache()
    out: dict[str, Any] = {}
    async with _client() as client:
        if "headers" in include:
            out["security_headers"] = grade_security_headers(headers or {})
        jobs = {
            "w3c": check_w3c, "ssllabs": check_ssllabs,
            "urlscan": check_urlscan_search,
            "pagespeed": check_pagespeed, "ranknibbler": check_ranknibbler,
        }
        pending = {name: fn(url, client, cache)
                   for name, fn in jobs.items() if name in include}
        for name, coro in pending.items():
            try:
                out[name] = await coro
            except Exception as exc:
                out[name] = {"source": name, "status": "skipped",
                             "reason": f"{type(exc).__name__}: {exc}"}
    out["keyed_sources_configured"] = {
        "pagespeed": bool(__import__("os").environ.get("PAGESPEED_API_KEY", "").strip()),
        "ranknibbler": bool(__import__("os").environ.get("RANKNIBBLER_API_KEY", "").strip()),
    }
    return out


def enrich_audit(audit: dict, headers: dict | None = None,
                 include: tuple[str, ...] = ("headers", "w3c", "ssllabs", "urlscan"),
                 cache: EnrichmentCache | None = None) -> dict:
    """Enrich an audit dict in place (sync wrapper for pipeline use).

    Loop-safe: works from plain sync code AND from inside a running event
    loop (e.g. ``website_auditor --enrich``). Prefer ``await enrich_async()``
    when you already have a loop.
    """
    enrichment = _run_coro(enrich_async(audit.get("url", ""), headers, cache, include))
    audit["enrichment"] = enrichment
    grading = (enrichment.get("security_headers") or {}).get("defects", [])
    if grading:
        audit.setdefault("defects", []).extend(grading)
        audit["defect_count"] = len(audit["defects"])
        try:  # re-score with the auditor's own scorer; never fail the audit
            import website_auditor as wa

            audit["score"] = wa.score_defects(audit["defects"])
        except Exception:
            pass
    return audit
