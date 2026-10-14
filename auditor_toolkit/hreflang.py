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

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    hreflang_links = [
        {"hreflang": str(tag.get("hreflang", "")), "href": str(tag.get("href", ""))}
        for tag in soup.find_all("link")
        if "alternate" in [str(rel).lower() for rel in tag.get("rel", [])]
        and tag.has_attr("hreflang")
    ]
    if not hreflang_links:
        return [], {"url": url, "hreflang_links": [], "hreflang_count": 0,
                    "limitation": "No multilingual annotations declared; reciprocity not fetched."}

    invalid = []
    valid_links = []
    for link in hreflang_links:
        lang = link["hreflang"].strip().lower()
        try:
            target = urlsplit(urljoin(url, link["href"]))
            valid = bool(link["href"].strip()) and target.scheme in {"http", "https"} and bool(target.hostname)
        except ValueError:
            valid = False
        if not valid or not re.fullmatch(r"(?:x-default|[a-z]{2,3}(?:-[a-z0-9]{2,8})*)", lang):
            invalid.append(link)
        else:
            valid_links.append(link)
    if invalid:
        findings.append(Finding(
            "hreflang-invalid", "Invalid hreflang annotation", f"{len(invalid)} invalid annotations",
            "medium", url, check="hreflang", evidence_source="dom:link[rel=alternate]",
            observed=str(invalid), remediation_action="Use valid language tags and HTTP(S) targets.",
        ))
    hreflang_links = valid_links

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
        "invalid_links": invalid,
        "limitation": "Declared annotations only; cross-page reciprocity was not fetched.",
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
            host = (urlsplit(urljoin(url, href)).hostname or "").lower().removeprefix("www.")
        except Exception:
            continue
        if host == canonical_host and urljoin(url, href).split("#")[0] == url.split("#")[0]:
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
                observed="No hreflang link points to this page URL",
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
