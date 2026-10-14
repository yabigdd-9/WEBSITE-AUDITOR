"""
Hreflang validation.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlsplit

from auditor_toolkit.checks import Finding


def analyse_html(html: str, url: str, headers: dict) -> tuple[list[Finding], dict[str, Any]]:
    """Analyse HTML for hreflang validation findings."""
    findings: list[Finding] = []
    origin = urlsplit(url)
    canonical_host = (origin.hostname or "").lower().removeprefix("www.")

    # Extract hreflang links from <link rel="alternate" hreflang="..."> tags
    hreflang_links: list[dict[str, str]] = []
    for match in re.finditer(
        r'<link\b[^>]*rel=["\']alternate["\'][^>]*hreflang=["\']([^"\']+)["\'][^>]*href=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    ):
        hreflang_links.append({"hreflang": match.group(1), "href": match.group(2)})

    # Also try the reverse attribute order
    for match in re.finditer(
        r'<link\b[^>]*href=["\']([^"\']+)["\'][^>]*hreflang=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    ):
        hreflang_links.append({"hreflang": match.group(2), "href": match.group(1)})

    # Deduplicate by hreflang
    seen: dict[str, str] = {}
    for link in hreflang_links:
        lang = link["hreflang"].lower().strip()
        if lang and lang not in seen:
            seen[lang] = link["href"]

    evidence = {
        "url": url,
        "hreflang_links": [
            {"hreflang": lang, "href": href} for lang, href in seen.items()
        ],
        "hreflang_count": len(seen),
    }

    # Check for x-default (recommended for multilingual sites)
    if "x-default" not in seen:
        findings.append(
            Finding(
                "hreflang-no-x-default",
                "Missing hreflang x-default",
                "No x-default link tag found",
                "low",
                url,
                check="hreflang",
                evidence_source="dom:link[rel=alternate][hreflang]",
                observed="No <link rel=\"alternate\" hreflang=\"x-default\"> tag present",
                business_impact="Search engines have no fallback language rule for "
                "users whose locale is not explicitly covered.",
                remediation_action="Add an hreflang=\"x-default\" link pointing to a "
                "neutral version of the page.",
                remediation_automation="AUTO_PREVIEW",
                effort_band="XS",
            )
        )

    # Check for self-referencing canonical hreflang
    self_ref = None
    for lang, href in seen.items():
        try:
            host = (urlsplit(href).hostname or "").lower().removeprefix("www.")
        except Exception:
            continue
        if host == canonical_host:
            self_ref = lang
            break

    if not self_ref:
        findings.append(
            Finding(
                "hreflang-no-self",
                "Missing self-referencing hreflang",
                "No hreflang link points back to this page",
                "medium",
                url,
                check="hreflang",
                evidence_source="dom:link[rel=alternate][hreflang]",
                observed="No hreflang link has the same host as this page",
                business_impact="Search engines may not recognise this page as the "
                "canonical version for its language.",
                remediation_action="Add an hreflang link for this page's language that "
                "points back to this URL.",
                remediation_automation="AUTO_PREVIEW",
                effort_band="XS",
            )
        )

    # Check for duplicate hreflang values
    if len(hreflang_links) != len(seen):
        findings.append(
            Finding(
                "hreflang-duplicate",
                "Duplicate hreflang values",
                f"{len(hreflang_links) - len(seen)} duplicate(s)",
                "low",
                url,
                check="hreflang",
                evidence_source="dom:link[rel=alternate][hreflang]",
                observed=f"{len(hreflang_links)} hreflang tags, {len(seen)} unique languages",
                business_impact="Duplicate hreflang declarations can confuse search "
                "engines about which page to show.",
                remediation_action="Remove duplicate hreflang link tags.",
                remediation_automation="AUTO_PREVIEW",
                effort_band="XS",
            )
        )

    return findings, evidence