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
        "framework_fill_images": 0,
        "external_images": 0,
        "large_file_hints": [],
    }

    for tag in img_tags:
        src = str(tag.get("src", ""))
        if tag.get("data-nimg") == "fill":
            evidence["framework_fill_images"] += 1
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
                "Space reservation needs rendered review; CSS or a sized container may already prevent layout shift",
                "low",
                url,
                check="images",
                confidence="heuristic",
                evidence_source="dom:img element",
                observed=f"{evidence['missing_dimensions']} of {evidence['image_count']} images do not provide positive numeric width and height attributes",
                business_impact="Layout shift is possible only if the rendered page does not "
                "already reserve image space. Static HTML alone does not establish CLS or its impact.",
                remediation_action="Inspect computed styles, container sizing and measured layout shifts. "
                "Add dimensions or equivalent space reservation only where needed; preserve intentional framework fill layouts.",
                remediation_automation="HUMAN_REVIEW",
                effort_band="S",
            )
        )

    # An absent loading attribute uses the browser's normal eager behaviour.
    # Static HTML cannot establish viewport placement or LCP. Keep the count as
    # evidence, without treating intentional eager hero/logo images as defects.

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
