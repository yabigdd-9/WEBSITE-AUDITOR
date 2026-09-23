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
    soup = BeautifulSoup(html, "html.parser")
    technologies = [
        technology
        for technology in (
            _detect_wordpress(soup),
            _detect_woocommerce(headers),
            _detect_shopify(soup, headers),
            _detect_wix(soup),
            _detect_squarespace(soup),
            _detect_react(soup),
            _detect_bootstrap(soup),
            _detect_jquery(soup),
            _detect_analytics(soup),
        )
        if technology is not None
    ]
    return technologies


def _technology(name: str, category: str, evidence: str, confidence: float) -> Technology:
    return Technology(
        technology=name,
        category=category,
        evidence=evidence,
        confidence=confidence,
    )


def _detect_wordpress(soup: BeautifulSoup) -> Technology | None:
    generator = soup.find("meta", attrs={"name": "generator"})
    generator_content = generator.get("content") if generator else None
    if not isinstance(generator_content, str) or "wordpress" not in generator_content.lower():
        return None

    content = generator_content.lower()
    version_match = re.search(r"wordpress\s+([\d.]+)", content)
    version = version_match.group(1) if version_match else None
    return Technology(
        technology="WordPress",
        category="CMS",
        version=version,
        version_confidence=0.9 if version else 0.7,
        evidence=f"meta generator: {content}",
        confidence=0.9 if version else 0.7,
    )


def _detect_woocommerce(headers: dict) -> Technology | None:
    cookie = headers.get("Set-Cookie", "")
    if "woocommerce" in cookie.lower():
        return _technology("WooCommerce", "Ecommerce", "WooCommerce cookie detected", 0.8)
    return None


def _detect_shopify(soup: BeautifulSoup, headers: dict) -> Technology | None:
    stage = headers.get("X-Shopify-Stage")
    if stage:
        return _technology("Shopify", "Ecommerce", f"X-Shopify-Stage header: {stage}", 0.9)
    if soup.find("script", src=re.compile(r"cdn\.shopify\.com")):
        return _technology("Shopify", "Ecommerce", "Shopify CDN script detected", 0.7)
    return None


def _detect_generator_cms(soup: BeautifulSoup, name: str, pattern: str) -> Technology | None:
    tag = soup.find("meta", attrs={"name": "generator", "content": re.compile(pattern, re.I)})
    if not tag:
        return None
    content = tag.get("content")
    if not isinstance(content, str):
        return None
    return _technology(name, "CMS", f"meta generator: {content}", 0.8)


def _detect_wix(soup: BeautifulSoup) -> Technology | None:
    return _detect_generator_cms(soup, "Wix", r"Wix\.com")


def _detect_squarespace(soup: BeautifulSoup) -> Technology | None:
    return _detect_generator_cms(soup, "Squarespace", "Squarespace")


def _detect_react(soup: BeautifulSoup) -> Technology | None:
    if soup.find(attrs={"data-reactroot": True}) or soup.find("script", src=re.compile(r"react")):
        return _technology("React", "JavaScript Framework", "React attributes or script detected", 0.6)
    return None


def _detect_bootstrap(soup: BeautifulSoup) -> Technology | None:
    if soup.find("link", href=re.compile(r"bootstrap")) or soup.find(
        "script", src=re.compile(r"bootstrap")
    ):
        return _technology("Bootstrap", "CSS Framework", "Bootstrap CSS or JS detected", 0.6)
    return None


def _detect_jquery(soup: BeautifulSoup) -> Technology | None:
    if soup.find("script", src=re.compile(r"jquery")):
        return _technology("jQuery", "JavaScript Library", "jQuery script detected", 0.6)
    return None


def _detect_analytics(soup: BeautifulSoup) -> Technology | None:
    if soup.find("script", src=re.compile(r"google-analytics")) or soup.find(
        string=re.compile(r"ga\(")
    ):
        return _technology("Google Analytics", "Analytics", "Google Analytics script detected", 0.6)
    return None


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
