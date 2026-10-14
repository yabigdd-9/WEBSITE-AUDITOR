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

    # Detect html lang attribute
    lang_match = re.search(
        r'<html\b[^>]*\blang=["\']([a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})?)["\']',
        html,
        re.IGNORECASE,
    )
    detected_lang = lang_match.group(1).lower() if lang_match else None

    # Detect content language via meta
    content_lang_match = re.search(
        r'<meta\b[^>]*http-equiv=["\']content-language["\'][^>]*content=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    content_lang = content_lang_match.group(1) if content_lang_match else None

    evidence = {
        "url": url,
        "html_lang": detected_lang,
        "meta_content_language": content_lang,
        "is_nz_domain": is_nz,
    }

    if not detected_lang:
        findings.append(
            Finding(
                "missing-html-lang",
                "Missing html lang attribute",
                "No <html lang=\"...\"> attribute found",
                "medium",
                url,
                check="language",
                evidence_source="dom:html element",
                observed="No lang attribute on the <html> element",
                business_impact="Screen readers and browsers cannot determine the "
                "page language; accessibility and SEO suffer.",
                remediation_action='Add a lang attribute to the <html> element, e.g. <html lang="en">',
                remediation_automation="AUTO_PREVIEW",
                effort_band="XS",
            )
        )

    if is_nz and detected_lang and detected_lang != "en":
        findings.append(
            Finding(
                "nz-domain-non-en-lang",
                "NZ domain with non-English lang",
                f"Domain .nz but lang={detected_lang}",
                "low",
                url,
                check="language",
                evidence_source="dom:html element",
                observed=f"<html lang=\"{detected_lang}\"> on a .nz domain",
                business_impact="NZ businesses typically serve English-speaking "
                "customers; a non-English lang may be intentional but should be reviewed.",
                remediation_action="Confirm the language is intentional for this NZ audience.",
                remediation_automation="HUMAN_REVIEW",
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