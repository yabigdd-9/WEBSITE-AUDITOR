"""Bounded broken-image discovery and verification."""
from __future__ import annotations

import asyncio
import urllib.parse
from typing import Any

import bs4
import httpx

from .network import NetworkSafetyError, SafeFetcher, robots_policy


def discover_image_urls(html: str, base_url: str, *, limit: int = 30) -> list[str]:
    soup = bs4.BeautifulSoup(html or "", "lxml")
    found: list[str] = []
    seen: set[str] = set()

    def add(raw: str | None) -> None:
        if not raw:
            return
        value = raw.strip()
        if not value or value.startswith("data:") or value.startswith("blob:"):
            return
        absolute = urllib.parse.urljoin(base_url, value)
        parsed = urllib.parse.urlsplit(absolute)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return
        normalized = urllib.parse.urlunsplit(
            (parsed.scheme.lower(), parsed.netloc, parsed.path or "/", parsed.query, "")
        )
        if normalized not in seen and len(found) < max(0, int(limit)):
            seen.add(normalized)
            found.append(normalized)

    for image in soup.find_all("img"):
        add(image.get("src"))
        srcset = str(image.get("srcset") or "")
        for candidate in srcset.split(","):
            add(candidate.strip().split(" ", 1)[0] if candidate.strip() else None)

    for source in soup.find_all("source"):
        srcset = str(source.get("srcset") or "")
        for candidate in srcset.split(","):
            add(candidate.strip().split(" ", 1)[0] if candidate.strip() else None)

    return found


async def audit_image_urls(
    session: httpx.AsyncClient,
    urls: list[str],
    *,
    user_agent: str,
    sample_limit: int = 12,
) -> tuple[list[dict], dict[str, Any]]:
    sampled = urls[: max(0, int(sample_limit))]
    broken: list[dict[str, Any]] = []
    checked: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    fetcher = SafeFetcher(
        session,
        timeout=8,
        max_redirects=5,
        max_body_bytes=64_000,
        per_domain_concurrency=2,
        delay_seconds=0.25,
    )
    sem = asyncio.Semaphore(4)

    async def inspect(url: str) -> None:
        async with sem:
            try:
                policy = await robots_policy(session, url, user_agent=user_agent, timeout=6)
                if not policy.get("allowed", True):
                    skipped.append({"url": url, "reason": "robots.txt disallowed"})
                    return
                response = await fetcher.head_status(url)
                record = {
                    "url": url,
                    "status": response.status,
                    "final_url": response.final_url,
                    "redirect_chain": response.redirect_chain,
                }
                checked.append(record)
                if response.status >= 400:
                    broken.append(record)
            except (httpx.HTTPError, NetworkSafetyError) as exc:
                skipped.append({"url": url, "reason": str(exc)})

    await asyncio.gather(*(inspect(url) for url in sampled))

    defects: list[dict] = []
    if broken:
        defects.append(
            {
                "defect": f"{len(broken)} broken image(s)",
                "impact": "Missing visual assets can reduce trust, usability, and conversion",
            }
        )
    return defects, {
        "discovered_count": len(urls),
        "sampled_count": len(sampled),
        "checked": checked,
        "broken": broken,
        "skipped": skipped,
    }
