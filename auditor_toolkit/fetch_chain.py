# P1 fetch chain: Lightpanda/Crawl4AI L1 -> Playwright L2 -> trafilatura/urllib L3.
# Pure-stdlib orchestration; optional deps imported lazily so P0 stays green without them.
from __future__ import annotations

import os
import urllib.request

FETCH_ORDER = ("l1", "l2", "l3")


def fetch_l1(url: str, timeout: int = 15) -> dict:
    """L1: Lightpanda CDP (LIGHTPANDA_URL) or Crawl4AI sidecar (CRAWL4AI_URL); raises if unconfigured."""
    import json
    import urllib.request
    target = os.getenv("LIGHTPANDA_URL") or os.getenv("CRAWL4AI_URL")
    if not target:
        raise RuntimeError("L1 fetcher not configured (set LIGHTPANDA_URL or CRAWL4AI_URL)")
    req = urllib.request.Request(target.rstrip("/") + "/fetch",
                                 data=json.dumps({"url": url}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return {"tier": "l1", "html": json.loads(r.read().decode())["html"]}


def fetch_l2(url: str, timeout: int = 20) -> dict:
    """L2: Playwright Chromium full render (existing browser.py path semantics)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            pg = b.new_page()
            pg.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            return {"tier": "l2", "html": pg.content()}
        finally:
            b.close()


def fetch_l3(url: str, timeout: int = 15) -> dict:
    """L3: plain urllib fallback (matches full-pipeline.py fetch semantics)."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (NZ)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return {"tier": "l3", "html": r.read().decode("utf-8", errors="replace")}


def fetch_chain(url: str, order: tuple = FETCH_ORDER) -> dict:
    errors = []
    for tier in order:
        try:
            fn = {"l1": fetch_l1, "l2": fetch_l2, "l3": fetch_l3}[tier]
            out = fn(url)
            out["errors"] = errors
            return out
        except Exception as exc:
            errors.append({"tier": tier, "error": str(exc)[:300]})
    raise RuntimeError(f"all fetch tiers failed: {errors}")
