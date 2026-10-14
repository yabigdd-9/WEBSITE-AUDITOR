"""
Language validation.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from auditor_toolkit.checks import Finding


def analyse_html(html: str, url: str, headers: dict) -> tuple[list[Finding], dict[str, Any]]:
    """Analyse HTML for language validation findings."""
    findings: list[Finding] = []
    origin = urlsplit(url)
    canonical_host = (origin.hostname or "").lower().removeprefix("www.")
    is_nz = canonical_host.endswith(".nz")

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    raw_lang = str(soup.html.get("lang", "")) if soup.html else ""
    detected_lang = raw_lang.strip().lower() or None
    if detected_lang and not re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})*", detected_lang):
        detected_lang = None
    meta = next((tag for tag in soup.find_all("meta")
                 if str(tag.get("http-equiv", "")).lower() == "content-language"), None)
    content_lang = str(meta.get("content", "")).strip() if meta else None

    evidence = {
        "url": url,
        "html_lang": detected_lang,
        "meta_content_language": content_lang,
        "is_nz_domain": is_nz,
        "limitation": "Declared language only; content language is not inferred from the domain.",
    }

    if not detected_lang:
        findings.append(
            Finding(
                "invalid-html-lang" if raw_lang.strip() else "missing-html-lang",
                "Missing html lang attribute",
                "No <html lang=\"...\"> attribute found",
                "medium",
                url,
                check="language",
                evidence_source="dom:html element",
                observed=f"Invalid lang declaration: {raw_lang}" if raw_lang.strip() else "No lang attribute on the <html> element",
                business_impact="Screen readers and browsers cannot determine the "
                "page language; accessibility and SEO suffer.",
                remediation_action='Add a lang attribute to the <html> element, e.g. <html lang="en">',
                remediation_automation="AUTO_PREVIEW",
                effort_band="XS",
            )
        )

    if content_lang and detected_lang:
        # Check for mismatch between html lang and meta content-language
        base_html = detected_lang.split("-")[0]
        base_meta = content_lang.split(",")[0].strip().split("-")[0].lower()
        if base_html != base_meta:
            findings.append(
                Finding(
                    "lang-mismatch",
                    "Language mismatch between html lang and meta content-language",
                    f"html lang={detected_lang}, meta content-language={content_lang}",
                    "low",
                    url,
                    check="language",
                    evidence_source="dom:html element + meta tag",
                    observed=f"html lang=\"{detected_lang}\" vs meta content-language=\"{content_lang}\"",
                    business_impact="Conflicting language signals can confuse search "
                    "engines and accessibility tools.",
                    remediation_action="Align the html lang attribute with the meta "
                    "content-language declaration.",
                    remediation_automation="AUTO_PREVIEW",
                    effort_band="XS",
                )
            )

    return findings, evidence
