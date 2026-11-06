"""Passive cookie/consent observations; never a legal compliance determination."""
from __future__ import annotations

import re
from typing import Any

from auditor_toolkit.checks import Finding


def analyse_html(html: str, url: str, headers: dict) -> tuple[list[Finding], dict[str, Any]]:
    """Static markup cannot prove cookies or rendered consent controls."""
    raise ValueError("Rendered cookie and consent capture required")


def analyse_rendered(data: dict, url: str) -> tuple[list[Finding], dict[str, Any]]:
    """Inventory cookies and visible controls before any audit interaction.

    Cookie purpose is a name-based hint, not permission or legal evidence. Cookie
    values are never included, including when callers supply them accidentally.
    """
    consent = data.get("consent")
    if not isinstance(consent, dict) or consent.get("interaction") != "none":
        raise ValueError("Passive consent capture unavailable")
    cookies = consent.get("cookies_before_interaction")
    banners = consent.get("visible_banners")
    if not isinstance(cookies, list) or not isinstance(banners, list):
        raise ValueError("Cookie or visible-consent observation unavailable")
    if len(cookies) > 1000 or len(banners) > 20:
        raise ValueError("Consent capture exceeds observation bounds")
    if any(not isinstance(item, dict) or not isinstance(item.get("name"), str)
           for item in cookies):
        raise ValueError("Malformed cookie observation")
    if any(not isinstance(item, dict) or not isinstance(item.get("controls"), list)
           or not all(isinstance(label, str) for label in item["controls"])
           for item in banners):
        raise ValueError("Malformed consent controls")
    inventory = [{key: cookie[key] for key in
                  ("name", "domain", "secure", "httpOnly", "sameSite") if key in cookie}
                 for cookie in cookies]
    labels = [label[:100] for banner in banners for label in banner["controls"][:20]]
    tracking_hints = sorted({cookie["name"] for cookie in cookies
                             if re.match(r"^(?:_ga(?:_|$)|_gid$|_fbp$|_fbc$)", cookie["name"])})
    evidence = {
        "url": url, "interaction": "none", "cookies_before_interaction": inventory,
        "visible_banner_count": len(banners), "visible_control_labels": labels,
        "tracking_cookie_name_hints": tracking_hints,
        "accept_control_observed": any(re.search(r"\b(?:accept|allow|agree)\b", label, re.I) for label in labels),
        "reject_control_observed": any(re.search(r"\b(?:reject|decline|deny)\b", label, re.I) for label in labels),
        "manage_control_observed": any(re.search(r"\b(?:manage|preferences|settings)\b", label, re.I) for label in labels),
        "limitation": "Passive bounded lab visit only. Cookie purpose and applicable consent obligations require human review; no choices were clicked, no consent was granted, and later behavior was not tested.",
    }
    findings = []
    if tracking_hints:
        findings.append(Finding(
            "tracking-cookie-before-choice", "Possible tracking cookies before any choice",
            "Cookie names suggest tracking; purpose requires review", "medium", url,
            check="cookie_consent", confidence="heuristic",
            evidence_source="browser:context.cookies before interaction",
            observed=", ".join(tracking_hints),
            remediation_action="Verify each cookie's purpose and whether it should wait for a consent choice.",
            remediation_automation="HUMAN_REVIEW",
        ))
    if banners and evidence["accept_control_observed"] and not (
        evidence["reject_control_observed"] or evidence["manage_control_observed"]
    ):
        findings.append(Finding(
            "consent-choice-controls-unobserved", "Reject or preference controls not observed",
            "Only an accept control was recognized in the visible banner", "low", url,
            check="cookie_consent", confidence="heuristic",
            evidence_source="browser:visible consent controls", observed=str(labels),
            remediation_action="Review whether users can decline or manage optional cookies with equivalent access.",
            remediation_automation="HUMAN_REVIEW",
        ))
    return findings, evidence
