"""Detect and classify location pages on a website.

Identifies branch/office/store/city/region pages and classifies them by type.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

PageClassification = Literal[
    "location",
    "service_area",
    "homepage",
    "other",
]


@dataclass(frozen=True)
class LocationPageFeatures:
    """Features extracted from a page for location-page classification."""

    url: str
    title: str = ""
    h1: str = ""
    has_address_on_page: bool = False
    has_phone_on_page: bool = False
    has_localbusiness_schema: bool = False
    has_breadcrumbs: bool = False
    breadcrumb_text: str = ""
    url_path_depth: int = 0
    url_segments: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "h1": self.h1,
            "has_address_on_page": self.has_address_on_page,
            "has_phone_on_page": self.has_phone_on_page,
            "has_localbusiness_schema": self.has_localbusiness_schema,
            "has_breadcrumbs": self.has_breadcrumbs,
            "breadcrumb_text": self.breadcrumb_text,
            "url_path_depth": self.url_path_depth,
            "url_segments": self.url_segments,
        }


@dataclass(frozen=True)
class LocationPage:
    """A classified location page."""

    url: str
    classification: PageClassification
    confidence: float = 0.0
    features: LocationPageFeatures | None = None
    detected_location_name: str = ""
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "classification": self.classification,
            "confidence": self.confidence,
            "features": self.features.to_dict() if self.features else None,
            "detected_location_name": self.detected_location_name,
            "reasons": self.reasons,
        }


# ---------------------------------------------------------------------------
# URL pattern signals
# ---------------------------------------------------------------------------

_LOCATION_PATH_PATTERNS = [
    # Direct location indicators
    r"/locations?/([^/]+)",
    r"/branches?/([^/]+)",
    r"/offices?/([^/]+)",
    r"/stores?/([^/]+)",
    r"/studios?/([^/]+)",
    r"/clinics?/([^/]+)",
    r"/agencies?/([^/]+)",
    # Region/city patterns (common in local SEO)
    r"/(christchurch|auckland|wellington|hamilton|tauranga|dunedin|rotorua|napier|nelson)/",
    r"/service-?area[s]?/([^/]+)",
    # "Near me" / geo-targeted
    r"/near-me/",
    r"/find-a-[^/]+/",
    r"/contact/[^/]+",
]

_SERVICE_AREA_PATTERNS = [
    r"/service-?area[s]?/",
    r"/areas?-served/",
    r"/coverage-?area[s]?/",
    r"/where-we-work/",
]

_HOMEPAGE_PATTERNS = [
    r"^/$",
    r"^/index\.(html|php|aspx?)$",
    r"^/home/?$",
]

# Location name indicators in page content
_LOCATION_INDICATOR_WORDS = frozenset(
    {
        "branch", "office", "location", "store", "studio",
        "clinic", "agency", "outlet", "centre", "center",
        "serving", "coverage", "area", "region",
    }
)


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------


def extract_location_features(
    url: str,
    html: str,
    title: str = "",
    headings: list[str] | None = None,
    has_address: bool = False,
    has_phone: bool = False,
    has_localbusiness_schema: bool = False,
    breadcrumbs: list[str] | None = None,
) -> LocationPageFeatures:
    """Extract classification features from a page.

    Callers may pre-extract some signals (address, phone, schema) to avoid
    re-parsing.
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    segments = [s for s in path.split("/") if s]

    breadcrumb_text = " > ".join(breadcrumbs) if breadcrumbs else ""
    has_breadcrumbs = len(breadcrumbs or []) >= 2

    return LocationPageFeatures(
        url=url,
        title=title,
        h1=(headings or [None for _ in range(1)])[0] if headings else "",
        has_address_on_page=has_address,
        has_phone_on_page=has_phone,
        has_localbusiness_schema=has_localbusiness_schema,
        has_breadcrumbs=has_breadcrumbs,
        breadcrumb_text=breadcrumb_text,
        url_path_depth=len(segments),
        url_segments=segments,
    )


def extract_features_from_html(
    url: str,
    html: str,
) -> LocationPageFeatures:
    """Extract features by parsing HTML directly."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    title = ""
    title_tag = soup.find("title")
    if title_tag is not None:
        title_content = title_tag.string
        if isinstance(title_content, str):
            title = title_content.strip()

    h1_tags = soup.find_all("h1")
    h1 = h1_tags[0].get_text(strip=True) if h1_tags else ""

    # Check for address patterns (simple heuristic)
    has_address = False
    for tag in soup.find_all(["address", "p", "div"]):
        text = tag.get_text().lower()
        if any(kw in text for kw in ("street", "road", "avenue", "new zealand", "nz ")):
            has_address = True
            break

    # Check for phone patterns
    has_phone = False
    for tag in soup.find_all(["a", "span", "p", "div"]):
        text = tag.get_text()
        if re.search(r"\+64|0\d{8,10}|\(\d{2}\)\s?\d{3,4}", text):
            has_phone = True
            break

    # Check for LocalBusiness schema
    has_schema = False
    for script in soup.find_all("script", type="application/ld+json"):
        script_content = script.string
        if script_content and any(
            kw in script_content for kw in ("LocalBusiness", '"address"', '"telephone"')
        ):
            has_schema = True
            break

    # Breadcrumbs
    breadcrumbs: list[str] = []
    bc_container = soup.find(
        ["nav", "div"],
        class_=re.compile(r"breadcrumb|breadcrumbs|nav", re.I),
    )
    if bc_container:
        links = bc_container.find_all("a")
        breadcrumbs = [a.get_text(strip=True) for a in links if a.get_text(strip=True)]

    return extract_location_features(
        url=url,
        html=html,
        title=title,
        headings=[h1] if h1 else [],
        has_address=has_address,
        has_phone=has_phone,
        has_localbusiness_schema=has_schema,
        breadcrumbs=breadcrumbs,
    )


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_location_page(features: LocationPageFeatures) -> LocationPage:
    """Classify a page based on extracted features.

    Returns a LocationPage with classification, confidence, and reasons.
    """
    path = _location_path(features.url)
    classification, score, reasons = _classify_location_path(path)
    if classification == "homepage":
        return LocationPage(
            url=features.url,
            classification=classification,
            confidence=score,
            features=features,
            reasons=reasons,
        )

    classification, score = _apply_schema_signal(
        features, classification, score, reasons
    )
    classification, score = _apply_address_signal(
        features, classification, score, reasons
    )
    score = _apply_phone_signal(features, score, reasons)
    classification, score = _apply_breadcrumb_signal(
        features, classification, score, reasons
    )
    classification, score = _apply_title_signal(
        features, classification, score, reasons
    )

    # Extract detected location name from URL
    location_name = _extract_location_name_from_url(features.url)

    classification, score = _apply_depth_signal(features, classification, score, reasons)

    confidence = round(score, 2)
    return LocationPage(
        url=features.url,
        classification=classification,
        confidence=confidence,
        features=features,
        detected_location_name=location_name,
        reasons=reasons,
    )


def _location_path(url: str) -> str:
    path = url.split("://", 1)[-1].split("/", 1)[-1] if "://" in url else ""
    return path if path.startswith("/") else "/" + path


def _classify_location_path(path: str) -> tuple[PageClassification, float, list[str]]:
    if any(re.search(pattern, path, re.I) for pattern in _HOMEPAGE_PATTERNS):
        return "homepage", 0.9, ["URL matches homepage pattern"]
    classification: PageClassification = "other"
    score = 0.0
    reasons: list[str] = []
    if any(re.search(pattern, path, re.I) for pattern in _SERVICE_AREA_PATTERNS):
        classification, score = "service_area", 0.7
        reasons.append("URL matches service-area pattern")
    if any(re.search(pattern, path, re.I) for pattern in _LOCATION_PATH_PATTERNS):
        classification, score = "location", max(score, 0.75)
        reasons.append("URL matches location pattern")
    return classification, score, reasons


def _apply_schema_signal(features, classification, score, reasons):
    if not features.has_localbusiness_schema:
        return classification, score
    if classification in ("location", "service_area"):
        score = min(score + 0.15, 1.0)
    else:
        classification, score = "location", max(score, 0.6)
    reasons.append("Has LocalBusiness schema")
    return classification, score


def _apply_address_signal(features, classification, score, reasons):
    if not features.has_address_on_page:
        return classification, score
    if classification == "other":
        classification, score = "location", max(score, 0.5)
    else:
        score = min(score + 0.1, 1.0)
    reasons.append("Has address on page")
    return classification, score


def _apply_phone_signal(features, score, reasons):
    if features.has_phone_on_page:
        score = min(score + 0.05, 1.0)
        reasons.append("Has phone on page")
    return score


def _apply_breadcrumb_signal(features, classification, score, reasons):
    location_terms = ("location", "branch", "office", "store")
    breadcrumb_text = features.breadcrumb_text.lower()
    if features.has_breadcrumbs and any(term in breadcrumb_text for term in location_terms):
        if classification == "other":
            classification, score = "location", max(score, 0.6)
        reasons.append("Breadcrumb indicates location")
    return classification, score


def _apply_title_signal(features, classification, score, reasons):
    title = (features.title + " " + features.h1).lower()
    for word in _LOCATION_INDICATOR_WORDS:
        if word in title:
            if classification == "other":
                classification, score = "location", max(score, 0.45)
            score = min(score + 0.05, 1.0)
            reasons.append(f"Title/H1 contains location indicator: {word}")
            break
    return classification, score


def _apply_depth_signal(features, classification, score, reasons):
    has_location_evidence = features.has_address_on_page or features.has_localbusiness_schema
    if classification == "other" and features.url_path_depth > 1 and has_location_evidence:
        classification, score = "location", 0.55
        reasons.append("Deep URL with location signals")
    return classification, score


def _extract_location_name_from_url(url: str) -> str:
    """Try to extract a location/city name from the URL path."""
    from urllib.parse import urlparse

    path = urlparse(url).path
    segments = [s for s in path.split("/") if s]

    # Look for common patterns: /locations/christchurch, /christchurch
    for i, seg in enumerate(segments):
        if seg.lower() in ("locations", "location", "branches", "branch",
                          "offices", "office", "stores", "store",
                          "areas", "area", "service-areas", "service-area"):
            if i + 1 < len(segments):
                return segments[i + 1].replace("-", " ").title()

    # If no container keyword, try the last meaningful segment
    skip = {"www", "http:", "https:", "index.html", "index.php"}
    meaningful = [s for s in segments if s.lower() not in skip]
    if meaningful:
        return meaningful[-1].replace("-", " ").title()

    return ""


# ---------------------------------------------------------------------------
# Bulk detection
# ---------------------------------------------------------------------------


def detect_location_pages(
    url_features: list[LocationPageFeatures],
) -> list[LocationPage]:
    """Classify a batch of pages and return only those that are locations
    or service-area pages."""
    results: list[LocationPage] = []
    for features in url_features:
        page = classify_location_page(features)
        if page.classification in ("location", "service_area"):
            results.append(page)
    return results


def scan_urls_for_location_patterns(urls: list[str]) -> list[str]:
    """Quick pre-filter: which URLs look like location pages by URL alone."""
    matching: list[str] = []
    for url in urls:
        path = url.split("://", 1)[-1].split("/", 1)[-1] if "://" in url else ""
        if not path.startswith("/"):
            path = "/" + path
        if any(re.search(pat, path, re.I) for pat in _LOCATION_PATH_PATTERNS + _SERVICE_AREA_PATTERNS):
            matching.append(url)
    return matching
