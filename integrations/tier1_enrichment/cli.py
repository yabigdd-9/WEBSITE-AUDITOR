"""CLI: ``python3 -m integrations.tier1_enrichment.cli <url> [--include ...]``.

Fetches the page head itself (HEAD request) so it works standalone, then
prints the enrichment JSON. Exit 0 even when every source skips.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from integrations.tier1_enrichment.cache import EnrichmentCache
from integrations.tier1_enrichment.enrich import enrich_async

SOURCES = ("headers", "w3c", "ssllabs", "urlscan", "pagespeed", "ranknibbler")


async def _head_headers(url: str) -> dict:
    try:
        import httpx

        async with httpx.AsyncClient(follow_redirects=True) as client:
            r = await client.head(url, timeout=15,
                                  headers={"User-Agent": "Mozilla/5.0 (NZ) WebsiteRescueAuditor/2.0"})
            return dict(r.headers)
    except Exception:
        return {}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Tier 1 enrichment probe (keyless-first)")
    p.add_argument("url", help="URL to enrich")
    p.add_argument("--include", nargs="+", default=["headers", "w3c", "ssllabs", "urlscan"],
                   choices=SOURCES, help="sources to query")
    p.add_argument("--output", "-o", help="write JSON here instead of stdout")
    args = p.parse_args(argv)

    async def _run():
        headers = await _head_headers(args.url)
        return await enrich_async(args.url, headers, EnrichmentCache(),
                                  include=tuple(args.include))

    result = asyncio.run(_run())
    text = json.dumps(result, indent=2, default=str)
    if args.output:
        open(args.output, "w").write(text)
        print(f"saved to {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
