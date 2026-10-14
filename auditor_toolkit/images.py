"""
Image optimization analysis.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from auditor_toolkit.checks import Finding


def analyse_html(html: str, url: str, headers: dict) -> tuple[list[Finding], dict[str, Any]]:
    """Analyse HTML for image optimization findings."""
    findings: list[Finding] = []
    origin = urlsplit(url)
    canonical_host = (origin.hostname or "").lower().removeprefix("www.")

    from bs4 import BeautifulSoup

    img_tags = BeautifulSoup(html, "lxml").find_all("img")
    evidence: dict[str, Any] = {
        "url": url,
        "image_count": len(img_tags),
        "missing_alt": 0,
        "missing_dimensions": 0,
        "missing_loading": 0,
        "external_images": 0,
        "large_file_hints": [],
    }

    for tag in img_tags:
        src = str(tag.get("src", ""))
        if not tag.has_attr("alt"):
            evidence["missing_alt"] += 1
        dimensions = [str(tag.get(key, "")) for key in ("width", "height")]
        if not all(value.isdigit() and int(value) > 0 for value in dimensions):
            evidence["missing_dimensions"] += 1
        if not tag.has_attr("loading"):
            evidence["missing_loading"] += 1
        if src.startswith(("http://", "https://", "//")):
            try:
                host = (urlsplit(src).hostname or "").lower().removeprefix("www.")
                if host and host != canonical_host:
                    evidence["external_images"] += 1
            except Exception:
                pass

    if evidence["missing_alt"] > 0:
        findings.append(
            Finding(
                "images-missing-alt",
                f"Images missing alt text ({evidence['missing_alt']})",
                "Screen readers cannot describe images; accessibility and SEO suffer",
                "medium",
                url,
                check="images",
                evidence_source="dom:img element",
                observed=f"{evidence['missing_alt']} of {evidence['image_count']} images have no alt text",
                business_impact="Screen readers announce 'image' instead of context. "
                "Search engines cannot index image content. Both hurt accessibility and SEO.",
                remediation_action="Add descriptive alt text to every informative image.",
                remediation_automation="AUTO_PREVIEW",
                effort_band="S",
            )
        )

    if evidence["missing_dimensions"] > 0:
        findings.append(
            Finding(
                "images-missing-dimensions",
                f"Images missing width/height ({evidence['missing_dimensions']})",
                "Layout shift risk; images without explicit dimensions cause CLS",
                "medium",
                url,
                check="images",
                evidence_source="dom:img element",
                observed=f"{evidence['missing_dimensions']} of {evidence['image_count']} images lack width and height attributes",
                business_impact="Images without explicit dimensions cause Cumulative "
                "Layout Shift (CLS), a Core Web Vital that hurts user experience and SEO.",
                remediation_action="Add explicit width and height attributes to all images.",
                remediation_automation="AUTO_PREVIEW",
                effort_band="S",
            )
        )

    if evidence["missing_loading"] > 0:
        findings.append(
            Finding(
                "images-missing-loading",
                f"Images missing loading attribute ({evidence['missing_loading']})",
                "No lazy-loading hint; below-the-fold images may load eagerly",
                "low",
                url,
                check="images",
                confidence="heuristic",
                evidence_source="dom:img element",
                observed=f"{evidence['missing_loading']} of {evidence['image_count']} images lack a loading attribute",
                business_impact="Images without loading=\"lazy\" may delay page "
                "interactivity and increase initial payload.",
                remediation_action='Add loading="lazy" to below-the-fold images.',
                remediation_automation="AUTO_PREVIEW",
                effort_band="XS",
            )
        )

    if evidence["external_images"] > 0:
        findings.append(
            Finding(
                "images-external-hosting",
                f"Images hosted externally ({evidence['external_images']})",
                "Third-party image dependency",
                "low",
                url,
                check="images",
                evidence_source="dom:img element",
                observed=f"{evidence['external_images']} image(s) served from external domains",
                business_impact="External images depend on third-party uptime and add "
                "DNS/HTTP overhead. Critical images should be self-hosted.",
                remediation_action="Self-host critical images or use a proven CDN with fallback.",
                remediation_automation="HUMAN_REVIEW",
                effort_band="M",
            )
        )

    return findings, evidence
