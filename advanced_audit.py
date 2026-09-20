#!/usr/bin/env python3
"""Advanced passive audit lane using the same public-network safety boundary."""
from __future__ import annotations

import argparse
import asyncio
import json
import urllib.parse

import httpx

from auditor_core.network import NetworkSafetyError, SafeFetcher, robots_policy
from auditor_core.passive import email_dns_security
from plugins.image_perf_auditor import audit_image_performance
from plugins.tech_stack_detector import detect_tech_stack
from plugins.ux_dark_pattern_scanner import scan_dark_patterns


USER_AGENT = "Mozilla/5.0 (NZ) WebsiteRescueAuditor/4.1 Advanced"


async def audit(url: str) -> dict:
    target = url if "://" in url else "https://" + url
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as session:
        try:
            robots = await robots_policy(session, target, user_agent=USER_AGENT, timeout=10)
        except NetworkSafetyError as exc:
            return {
                "url": target,
                "audit_state": "blocked",
                "reason": str(exc),
                "evidence": {"robots": {"allowed": False, "reason": str(exc)}},
            }

        if not robots.get("allowed", True):
            return {
                "url": target,
                "audit_state": "skipped",
                "reason": robots.get("reason", "robots.txt disallowed audit"),
                "evidence": {"robots": robots},
            }

        fetcher = SafeFetcher(
            session,
            timeout=15,
            max_redirects=5,
            max_body_bytes=5_000_000,
            per_domain_concurrency=2,
            delay_seconds=max(0.25, float(robots.get("crawl_delay") or 0)),
        )
        try:
            response = await fetcher.get_text(target)
        except (httpx.HTTPError, NetworkSafetyError) as exc:
            return {
                "url": target,
                "audit_state": "error",
                "reason": str(exc),
                "evidence": {"robots": robots},
            }

    parsed = urllib.parse.urlsplit(response.final_url)
    domain = parsed.hostname or ""
    headers = dict(response.headers)
    normalized_headers = dict(headers)
    normalized_headers.update({str(key).title(): value for key, value in headers.items()})

    email_signal = "@" in response.text
    dns_defects, email_dns = await asyncio.to_thread(
        email_dns_security,
        domain,
        email_signal=email_signal,
    )

    return {
        "schema_version": 2,
        "auditor_version": "4.1.0",
        "url": target,
        "final_url": response.final_url,
        "domain": domain,
        "audit_state": "completed",
        "network": {
            "status": response.status,
            "bytes_read": response.bytes_read,
            "redirect_chain": response.redirect_chain,
            "robots": robots,
        },
        "tech_stack_detected": sorted(detect_tech_stack(response.text, normalized_headers)),
        "email_security_dns": email_dns,
        "email_security_findings": dns_defects,
        "ux_dark_patterns": scan_dark_patterns(response.text),
        "image_performance": audit_image_performance(response.text),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Advanced passive Website Auditor checks")
    parser.add_argument("url")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(audit(args.url)), indent=2, default=str))


if __name__ == "__main__":
    main()
