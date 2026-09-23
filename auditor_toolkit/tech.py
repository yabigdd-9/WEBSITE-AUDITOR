"""
Technology detection for websites.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, List, Optional

from bs4 import BeautifulSoup

from auditor_toolkit.checks import Finding


@dataclass
class Technology:
    technology: str
    category: str
    version: Optional[str] = None
    version_confidence: float = 0.0
    evidence: str = ""
    confidence: float = 0.0


def detect_technology(html: str, url: str, headers: dict) -> List[Technology]:
    """Detect technologies used by the website."""
    technologies = []
    soup = BeautifulSoup(html, "html.parser")

    # WordPress detection via meta generator
    generator = soup.find("meta", attrs={"name": "generator"})
    generator_content = generator.get("content") if generator else None
    if isinstance(generator_content, str):
        content = generator_content.lower()
        if "wordpress" in content:
            # Try to extract version
            version_match = re.search(r"wordpress\s+([\d.]+)", content)
            version = version_match.group(1) if version_match else None
            tech = Technology(
                technology="WordPress",
                category="CMS",
                version=version,
                version_confidence=0.9 if version else 0.7,
                evidence=f"meta generator: {content}",
                confidence=0.9 if version else 0.7,
            )
            technologies.append(tech)

    # WooCommerce detection via WooCommerce cookie or header
    # Check for WooCommerce in Set-Cookie header
    set_cookie = headers.get("Set-Cookie", "")
    if "woocommerce" in set_cookie.lower():
        tech = Technology(
            technology="WooCommerce",
            category="Ecommerce",
            version=None,
            version_confidence=0.0,
            evidence="WooCommerce cookie detected",
            confidence=0.8,
        )
        technologies.append(tech)

    # Shopify detection via Shopify header or Shopify.myshopify.com in URLs
    shopify_header = headers.get("X-Shopify-Stage")
    if shopify_header:
        tech = Technology(
            technology="Shopify",
            category="Ecommerce",
            version=None,
            version_confidence=0.0,
            evidence=f"X-Shopify-Stage header: {shopify_header}",
            confidence=0.9,
        )
        technologies.append(tech)
    else:
        # Check for Shopify in HTML (e.g., CDN links)
        if soup.find("script", src=re.compile(r"cdn\.shopify\.com")):
            tech = Technology(
                technology="Shopify",
                category="Ecommerce",
                version=None,
                version_confidence=0.0,
                evidence="Shopify CDN script detected",
                confidence=0.7,
            )
            technologies.append(tech)

    # Wix detection via Wix.com in meta or HTML
    wix_meta = soup.find("meta", attrs={"name": "generator", "content": re.compile(r"Wix\.com", re.I)})
    if wix_meta:
        tech = Technology(
            technology="Wix",
            category="CMS",
            version=None,
            version_confidence=0.0,
            evidence=f"meta generator: {wix_meta.get('content')}",
            confidence=0.8,
        )
        technologies.append(tech)

    # Squarespace detection via Squarespace meta generator
    squarespace_meta = soup.find("meta", attrs={"name": "generator", "content": re.compile(r"Squarespace", re.I)})
    if squarespace_meta:
        tech = Technology(
            technology="Squarespace",
            category="CMS",
            version=None,
            version_confidence=0.0,
            evidence=f"meta generator: {squarespace_meta.get('content')}",
            confidence=0.8,
        )
        technologies.append(tech)

    # React detection via react-checksum or data-reactroot
    if soup.find(attrs={"data-reactroot": True}) or soup.find("script", src=re.compile(r"react")):
        tech = Technology(
            technology="React",
            category="JavaScript Framework",
            version=None,
            version_confidence=0.0,
            evidence="React attributes or script detected",
            confidence=0.6,
        )
        technologies.append(tech)

    # Bootstrap detection via Bootstrap CSS or JS
    if soup.find("link", href=re.compile(r"bootstrap")) or soup.find("script", src=re.compile(r"bootstrap")):
        tech = Technology(
            technology="Bootstrap",
            category="CSS Framework",
            version=None,
            version_confidence=0.0,
            evidence="Bootstrap CSS or JS detected",
            confidence=0.6,
        )
        technologies.append(tech)

    # jQuery detection via jQuery script
    if soup.find("script", src=re.compile(r"jquery")):
        tech = Technology(
            technology="jQuery",
            category="JavaScript Library",
            version=None,
            version_confidence=0.0,
            evidence="jQuery script detected",
            confidence=0.6,
        )
        technologies.append(tech)

    # Google Analytics detection via GA script
    if soup.find("script", src=re.compile(r"google-analytics")) or soup.find(text=re.compile(r"ga\(")):
        tech = Technology(
            technology="Google Analytics",
            category="Analytics",
            version=None,
            version_confidence=0.0,
            evidence="Google Analytics script detected",
            confidence=0.6,
        )
        technologies.append(tech)

    return technologies


def analyse_html(html: str, url: str, headers: dict) -> tuple[List[Finding], dict[str, Any]]:
    """Analyse HTML for technology findings."""
    techs = detect_technology(html, url, headers)
    findings = []
    for tech in techs:
        if tech.technology:
            findings.append(
                Finding(
                    defect_key=f"technology_{tech.technology.lower().replace(' ', '_')}",
                )
            )
    return findings, {"technologies": [t.__dict__ for t in techs]}

