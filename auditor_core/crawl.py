"""Same-origin crawl helpers for profile-driven multi-page audits."""
from __future__ import annotations

import urllib.parse
from typing import Iterable

import bs4


SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "data:", "blob:")


def discover_internal_links(html: str, base_url: str, *, limit: int = 100) -> list[str]:
    parsed_base = urllib.parse.urlsplit(base_url)
    origin = (parsed_base.scheme.lower(), parsed_base.hostname.lower() if parsed_base.hostname else "")
    soup = bs4.BeautifulSoup(html or "", "lxml")
    found: list[str] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        raw = str(anchor.get("href") or "").strip()
        if not raw or raw.startswith("#") or raw.lower().startswith(SKIP_SCHEMES):
            continue
        absolute = urllib.parse.urljoin(base_url, raw)
        parsed = urllib.parse.urlsplit(absolute)
        if parsed.scheme.lower() not in {"http", "https"}:
            continue
        host = parsed.hostname.lower() if parsed.hostname else ""
        if (parsed.scheme.lower(), host) != origin:
            continue
        normalized = urllib.parse.urlunsplit(
            (parsed.scheme.lower(), parsed.netloc, parsed.path or "/", parsed.query, "")
        )
        if normalized not in seen:
            seen.add(normalized)
            found.append(normalized)
        if len(found) >= max(0, int(limit)):
            break
    return found


def merge_site_findings(page_results: Iterable[dict]) -> list[dict]:
    merged: list[dict] = []
    for page in page_results:
        page_url = page.get("url")
        for finding in page.get("findings", []):
            if not isinstance(finding, dict):
                continue
            item = dict(finding)
            item["page_url"] = page_url
            merged.append(item)
    return merged
