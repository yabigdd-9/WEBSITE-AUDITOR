"""Orchestrator: run enrichment and merge it into an audit dict.

Contract:
- Attach per-source results to audit["enrichment"].
- Canonical evidence-based reports retain their defects and all score fields;
  enrichment is advisory pending a pipeline evidence adapter.
- Legacy {defect, impact} reports may append new header-grading defects and
  recompute the explicitly labelled compatibility score.

Source failures are recorded as skipped; malformed grading is held explicitly.
No source success or score update is inferred from an exception.
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
    try:
        enrichment = _run_coro(enrich_async(audit.get("url", ""), headers, cache, include))
    except Exception as error:
        audit["enrichment"] = {"status": "skipped", "reason": type(error).__name__}
        return audit
    audit["enrichment"] = enrichment
    grading = (enrichment.get("security_headers") or {}).get("defects", [])
    if grading:
        if not isinstance(grading, list) or any(
            not isinstance(row, dict)
            or not isinstance(row.get("defect"), str)
            or not isinstance(row.get("impact"), str)
            for row in grading
        ):
            enrichment["scoring"] = {"status": "HELD", "reason": "Unsupported header-grading defect shape"}
            return audit
        canonical = any(key in audit for key in (
            "schema_version", "severity_score", "health_score", "breakdown", "scoring",
        ))
        if canonical:
            enrichment["scoring"] = {
                "status": "ADVISORY_NOT_APPLIED",
                "reason": "Canonical findings require evidence-linked pipeline integration; scores preserved",
            }
            return audit
        from auditor_toolkit.legacy_scoring import LEGACY_SCORE_METHODS, score_legacy_defects

        method = audit.get("legacy_score_method")
        if method not in LEGACY_SCORE_METHODS:
            enrichment["scoring"] = {
                "status": "HELD",
                "reason": "Legacy scoring method is unrecorded or unsupported; findings and score preserved",
            }
            return audit
        existing = audit.get("defects", [])
        if not isinstance(existing, list) or any(not isinstance(row, dict) for row in existing):
            enrichment["scoring"] = {"status": "HELD", "reason": "Unsupported legacy defect shape"}
            return audit
        combined = list(existing)
        seen = {(row.get("defect"), row.get("impact")) for row in existing
                if isinstance(row.get("defect"), str) and isinstance(row.get("impact"), str)}
        for row in grading:
            identity = (row.get("defect"), row.get("impact"))
            if identity not in seen:
                combined.append(row)
                seen.add(identity)
        try:
            value = score_legacy_defects(combined, method=method)
            audit.update(defects=combined, defect_count=len(combined), score=value)
            enrichment["scoring"] = {"status": "UPDATED", "method": method}
        except (ValueError, TypeError):
            enrichment["scoring"] = {
                "status": "HELD", "reason": "Legacy score could not be recomputed; previous score preserved",
            }
    return audit
