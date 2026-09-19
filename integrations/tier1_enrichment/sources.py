"""Third-party source clients. Every function is key-optional where the
service allows it, honours its own TTL, and fails closed to ``skipped``.

Rate-limit etiquette (live-verified 2026-09-19):
- W3C Nu validator: keyless, generous; ``?out=json`` + UA header.
- SSL Labs v3: keyless but strict ToS — cached reads only
  (``startNew=off, fromCache=on``), long TTL, never hammer.
- urlscan.io search: keyless reads allowed (shared 1k searches/day quota);
  scan *submission* needs a key so it is deliberately NOT implemented here.
- PageSpeed Insights v5: keyless quota is shared and 429s often; with a free
  ``PAGESPEED_API_KEY`` it is ~25k req/day. Slow endpoint — long timeout.
- RankNibbler: needs ``RANKNIBBLER_API_KEY`` (free 100 req/day). Skipped
  cleanly without one.
"""

from __future__ import annotations

import os
import re
import urllib.parse
from typing import Any

try:  # httpx is already a repo dependency (requirements.txt)
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore

from integrations.tier1_enrichment.cache import EnrichmentCache

UA = {"User-Agent": "Mozilla/5.0 (NZ) WebsiteRescueAuditor/2.0 enrichment/1.0"}

TTL_W3C = 7 * 86400
TTL_SSLLABS = 7 * 86400
TTL_URLSCAN = 86400
TTL_PAGESPEED = 86400
TTL_RANKNIBBLER = 86400


def _norm_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    return url if url.startswith("http") else "https://" + url


def _domain(url: str) -> str:
    m = re.match(r"https?://([^/:]+)", _norm_url(url))
    return m.group(1) if m else url


async def _get_json(client, url: str, timeout: float,
                    headers: dict | None = None, params: dict | None = None) -> Any | None:
    try:
        r = await client.get(url, timeout=timeout, headers=headers or UA, params=params)
        if r.status_code == 200:
            return r.json()
        return {"_http_status": r.status_code}
    except Exception as exc:  # network, timeout, decode — all fail closed
        return {"_error": f"{type(exc).__name__}: {exc}"}


async def check_w3c(url: str, client, cache: EnrichmentCache) -> dict:
    """Keyless HTML validation via the W3C Nu validator (verified live)."""
    target = _norm_url(url)
    key = f"w3c:{target}"
    data, fresh = cache.get(key, TTL_W3C)
    if fresh:
        return {"source": "w3c", "cached": True, **data}
    payload = {"errors": 0, "error_list": [], "status": "ok"}
    doc = "https://validator.w3.org/nu/?out=json&doc=" + urllib.parse.quote(target, safe="")
    raw = await _get_json(client, doc, 25)
    if isinstance(raw, dict) and "_error" not in raw and "_http_status" not in raw:
        msgs = raw.get("messages", []) if isinstance(raw, dict) else []
        errs = [m for m in msgs if m.get("type") == "error"][:10]
        payload = {
            "errors": len([m for m in msgs if m.get("type") == "error"]),
            "error_list": [{"message": m.get("message"), "line": m.get("lastLine")} for m in errs],
            "status": "ok",
        }
    elif isinstance(raw, dict):
        payload = {"status": "skipped",
                   "reason": raw.get("_error") or f"http {raw.get('_http_status')}"}
    if payload.get("status") == "ok":
        cache.set(key, payload)
    return {"source": "w3c", "cached": False, **payload}


async def check_ssllabs(url: str, client, cache: EnrichmentCache) -> dict:
    """Keyless deep-TLS grade, cached reads only (respects Qualys ToS)."""
    host = _domain(url)
    key = f"ssllabs:{host}"
    data, fresh = cache.get(key, TTL_SSLLABS)
    if fresh:
        return {"source": "ssllabs", "cached": True, **data}
    raw = await _get_json(
        client, "https://api.ssllabs.com/api/v3/analyze", 30,
        params={"host": host, "startNew": "off", "fromCache": "on", "all": "done"},
    )
    payload: dict = {"status": "skipped", "reason": "no cached assessment yet"}
    if isinstance(raw, dict) and raw.get("status") == "READY" and raw.get("endpoints"):
        grades = [e.get("grade") for e in raw["endpoints"] if e.get("grade")]
        # SSL Labs grades sort A+..F as strings, so max() = worst grade
        payload = {"status": "ok", "grade": max(grades) if grades else None,
                   "endpoint_grades": grades}
    elif isinstance(raw, dict) and raw.get("status") not in (None, "READY"):
        payload = {"status": "pending", "reason": f"assessment status: {raw.get('status')}"}
    if payload.get("status") == "ok":
        cache.set(key, payload)
    return {"source": "ssllabs", "cached": False, **payload}


async def check_urlscan_search(url: str, client, cache: EnrichmentCache) -> dict:
    """Keyless urlscan.io search: has this host been seen/scanned before?"""
    host = _domain(url)
    key = f"urlscan:{host}"
    data, fresh = cache.get(key, TTL_URLSCAN)
    if fresh:
        return {"source": "urlscan", "cached": True, **data}
    raw = await _get_json(
        client, "https://urlscan.io/api/v1/search/", 20,
        params={"q": f"page.domain:{host}", "size": 5},
    )
    payload = {"status": "skipped", "reason": "search unavailable"}
    if isinstance(raw, dict) and isinstance(raw.get("results"), list):
        results = raw["results"][:5]
        payload = {
            "status": "ok",
            "scan_count": raw.get("total", len(results)),
            "recent": [{"url": (r.get("page") or {}).get("url"),
                        "time": (r.get("task") or {}).get("time")} for r in results],
        }
    if payload.get("status") == "ok":
        cache.set(key, payload)
    return {"source": "urlscan", "cached": False, **payload}


async def check_pagespeed(url: str, client, cache: EnrichmentCache) -> dict:
    """Lighthouse lab data via PageSpeed Insights v5.

    Works keyless for one-offs (shared quota 429s often) and properly with a
    free ``PAGESPEED_API_KEY``. Slow endpoint: 60s timeout.
    """
    target = _norm_url(url)
    key = f"pagespeed:{target}"
    data, fresh = cache.get(key, TTL_PAGESPEED)
    if fresh:
        return {"source": "pagespeed", "cached": True, **data}
    params: dict = {
        "url": target, "strategy": "mobile",
        "category": ["performance", "accessibility", "best-practices", "seo"],
    }
    api_key = os.environ.get("PAGESPEED_API_KEY", "").strip()
    if api_key:
        params["key"] = api_key
    raw = await _get_json(
        client, "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
        60, params=params,
    )
    if isinstance(raw, dict) and raw.get("lighthouseResult"):
        cats = (raw["lighthouseResult"].get("categories") or {})
        payload = {"status": "ok", "keyed": bool(api_key),
                   "scores": {k: (v or {}).get("score") for k, v in cats.items()}}
        cache.set(key, payload)
        return {"source": "pagespeed", "cached": False, **payload}
    reason = "quota/error"
    if isinstance(raw, dict):
        reason = raw.get("_error") or f"http {raw.get('_http_status')}" or reason
    return {"source": "pagespeed", "cached": False, "status": "skipped",
            "reason": reason, "keyed": bool(api_key)}


async def check_ranknibbler(url: str, client, cache: EnrichmentCache) -> dict:
    """On-page SEO breakdown via RankNibbler (free 100 req/day, key required)."""
    api_key = os.environ.get("RANKNIBBLER_API_KEY", "").strip()
    if not api_key:
        return {"source": "ranknibbler", "status": "skipped",
                "reason": "RANKNIBBLER_API_KEY not set (free 100/day at ranknibbler.com)"}
    target = _norm_url(url)
    key = f"ranknibbler:{target}"
    data, fresh = cache.get(key, TTL_RANKNIBBLER)
    if fresh:
        return {"source": "ranknibbler", "cached": True, **data}
    try:
        r = await client.get(
            "https://www.ranknibbler.com/api/v1/audit", timeout=45, headers=UA,
            params={"url": target, "key": api_key},
        )
        raw = r.json() if getattr(r, "status_code", None) == 200 \
            else {"_http_status": getattr(r, "status_code", None)}
    except Exception as exc:
        raw = {"_error": f"{type(exc).__name__}: {exc}"}
    if isinstance(raw, dict) and "_error" not in raw and "_http_status" not in raw:
        payload = {"status": "ok", "audit": raw}
        cache.set(key, payload)
        return {"source": "ranknibbler", "cached": False, **payload}
    reason = raw.get("_error") or f"http {raw.get('_http_status')}" \
        if isinstance(raw, dict) else "error"
    return {"source": "ranknibbler", "cached": False, "status": "skipped",
            "reason": reason}
