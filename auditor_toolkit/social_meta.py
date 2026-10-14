"""
Social media metadata analysis.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from auditor_toolkit.checks import Finding


def analyse_html(html: str, url: str, headers: dict) -> tuple[list[Finding], dict[str, Any]]:
    """Analyse HTML for social media metadata findings."""
    findings: list[Finding] = []
    evidence: dict[str, Any] = {"url": url, "og_tags": {}, "twitter_tags": {}}

    # Extract Open Graph tags
    og_tags: dict[str, str] = {}
    for match in re.finditer(
        r"""<meta\b[^>]*property=["']og:([\w:]+)["'][^>]*content=["']([^"']+)["']""",
        html,
        re.IGNORECASE,
    ):
        og_tags[match.group(1).lower()] = match.group(2)
    # Also try reverse attribute order
    for match in re.finditer(
        r"""<meta\b[^>]*content=["']([^"']+)["'][^>]*property=["']og:([\w:]+)["']""",
        html,
        re.IGNORECASE,
    ):
        og_tags[match.group(2).lower()] = match.group(1)

    # Extract Twitter Card tags
    twitter_tags: dict[str, str] = {}
    for match in re.finditer(
        r"""<meta\b[^>]*name=["']twitter:([\w:]+)["'][^>]*content=["']([^"']+)["']""",
        html,
        re.IGNORECASE,
    ):
        twitter_tags[match.group(1).lower()] = match.group(2)
    for match in re.finditer(
        r"""<meta\b[^>]*content=["']([^"']+)["'][^>]*name=["']twitter:([\w:]+)["']""",
        html,
        re.IGNORECASE,
    ):
        twitter_tags[match.group(2).lower()] = match.group(1)

    evidence["og_tags"] = og_tags
    evidence["twitter_tags"] = twitter_tags

    # Check for og:title
    if not og_tags.get("title"):
        findings.append(
            Finding(
                "social-meta-og-title",
                "Missing og:title",
                "No Open Graph title for social sharing",
                "medium",
                url,
                check="social_meta",
                evidence_source="dom:meta[property=og:title]",
                observed="No <meta property=\"og:title\"> tag present",
                business_impact="When this page is shared on social platforms, the "
                "default page title is used instead of a custom share title.",
                remediation_action="Add an og:title meta tag with a compelling share title.",
                remediation_automation="AUTO_PREVIEW",
                effort_band="XS",
            )
        )

    # Check for og:description
    if not og_tags.get("description"):
        findings.append(
            Finding(
                "social-meta-og-description",
                "Missing og:description",
                "No Open Graph description for social sharing",
                "medium",
                url,
                check="social_meta",
                evidence_source="dom:meta[property=og:description]",
                observed="No <meta property=\"og:description\"> tag present",
                business_impact="Social shares show generic text instead of a "
                "compelling description, reducing click-through from shares.",
                remediation_action="Add an og:description meta tag (120-200 chars).",
                remediation_automation="AUTO_PREVIEW",
                effort_band="XS",
            )
        )

    # Check for og:image
    if not og_tags.get("image"):
        findings.append(
            Finding(
                "social-meta-og-image",
                "Missing og:image",
                "No Open Graph image for social sharing",
                "medium",
                url,
                check="social_meta",
                evidence_source="dom:meta[property=og:image]",
                observed="No <meta property=\"og:image\"> tag present",
                business_impact="Social shares show no thumbnail, reducing visual "
                "appeal and click-through.",
                remediation_action="Add an og:image meta tag pointing to a 1200x630 image.",
                remediation_automation="AUTO_PREVIEW",
                effort_band="XS",
            )
        )

    # Check for og:type
    if not og_tags.get("type"):
        findings.append(
            Finding(
                "social-meta-og-type",
                "Missing og:type",
                "No Open Graph type declared",
                "low",
                url,
                check="social_meta",
                evidence_source="dom:meta[property=og:type]",
                observed="No <meta property=\"og:type\"> tag present",
                business_impact="Social platforms may not know how to render this "
                "page as a preview card.",
                remediation_action='Add an og:type meta tag (e.g. "website" or "article").',
                remediation_automation="AUTO_PREVIEW",
                effort_band="XS",
            )
        )

    # Check for Twitter Card
    if not twitter_tags.get("card"):
        findings.append(
            Finding(
                "social-meta-twitter-card",
                "Missing Twitter Card",
                "No twitter:card declared",
                "low",
                url,
                check="social_meta",
                evidence_source="dom:meta[name=twitter:card]",
                observed="No <meta name=\"twitter:card\"> tag present",
                business_impact="Twitter/X shares show no image or rich preview.",
                remediation_action='Add a twitter:card meta tag (e.g. "summary_large_image").',
                remediation_automation="AUTO_PREVIEW",
                effort_band="XS",
            )
        )

    # Check for Twitter handle
    if not twitter_tags.get("site") and not twitter_tags.get("creator"):
        findings.append(
            Finding(
                "social-meta-twitter-handle",
                "Missing Twitter handle",
                "No twitter:site or twitter:creator declared",
                "low",
                url,
                check="social_meta",
                evidence_source="dom:meta[name=twitter:site]",
                observed="No <meta name=\"twitter:site\"> or twitter:creator tag present",
                business_impact="Twitter/X attribution is missing; the account that "
                "shares this page is not tagged.",
                remediation_action="Add a twitter:site meta tag with your @handle.",
                remediation_automation="AUTO_PREVIEW",
                effort_band="XS",
            )
        )

    return findings, evidence