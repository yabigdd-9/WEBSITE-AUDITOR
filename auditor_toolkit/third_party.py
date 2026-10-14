"""
Third-party request inventory.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from auditor_toolkit.checks import Finding


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def analyse_html(html: str, url: str, headers: dict) -> tuple[list[Finding], dict[str, Any]]:
    """Analyse HTML for third-party request findings."""
    findings: list[Finding] = []
    origin = _origin(url)

    # Extract external domains from script, iframe, img, link, and source tags
    external: dict[str, int] = {}
    for tag, attr in (
        ("script", "src"),
        ("iframe", "src"),
        ("img", "src"),
        ("link", "href"),
        ("source", "src"),
    ):
        import re

        for match in re.finditer(
            rf"<{tag}\b[^>]*{attr}=[\"']([^\"']+)[\"']", html, re.IGNORECASE
        ):
            value = match.group(1)
            if value.startswith(("http://", "https://", "//")):
                try:
                    ext_origin = _origin(value)
                except Exception:
                    continue
                if ext_origin and ext_origin != origin:
                    external[ext_origin] = external.get(ext_origin, 0) + 1

    evidence = {
        "url": url,
        "external_domains": sorted(external),
        "external_request_count": sum(external.values()),
    }

    if external:
        findings.append(
            Finding(
                "third-party-requests",
                "Third-party requests detected",
                f"{len(external)} external domains, {sum(external.values())} requests",
                "medium",
                url,
                check="third-party",
                evidence_source="dom:external resource attributes",
                observed=f"{len(external)} external domains referenced: {', '.join(sorted(external))}",
                business_impact="Third-party scripts and assets add page weight, create "
                "privacy/cookie exposure, and can break if the vendor changes or goes down.",
                remediation_action="Audit each third-party domain; remove unused ones and "
                "consider self-hosting critical assets.",
                remediation_automation="HUMAN_REVIEW",
                effort_band="M",
            )
        )

    return findings, evidence