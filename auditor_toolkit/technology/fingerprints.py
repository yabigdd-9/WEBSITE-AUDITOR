"""Typed compatibility views over the canonical passive signature interpreter."""

from __future__ import annotations

from .observations import observe_technologies
from .schema import TechDetection, TechFingerprint

PRIORITY = {
    "cms": ("WordPress", "Shopify", "Wix", "Squarespace", "Webflow"),
    "framework": ("React", "Angular", "Vue", "jQuery", "Bootstrap"),
    "server": ("Nginx", "Apache", "IIS", "Cloudflare", "LiteSpeed"),
    "analytics": (
        "Google Analytics",
        "Google Tag Manager",
        "Hotjar",
        "Microsoft Clarity",
        "Facebook Pixel",
    ),
    "cdn": ("Cloudflare", "CloudFront", "Fastly", "Akamai"),
    "ecommerce": ("WooCommerce", "Magento", "BigCommerce"),
    "payment": ("Stripe", "PayPal", "Square"),
    "language": ("PHP", "Python", "Node.js", "Ruby", "ASP.NET"),
}


def _priority(row):
    names = PRIORITY.get(row["category"], ())
    return (names.index(row["name"]) if row["name"] in names else len(names), row["name"])


def _rows(html="", headers=None, category=""):
    return sorted(
        [row for row in observe_technologies(html, headers) if row["category"] == category],
        key=_priority,
    )


def _detection(row):
    name = "nginx" if row["name"] == "Nginx" else row["name"]
    return TechDetection(
        name=name,
        category=row["category"],
        confidence=row["confidence"],
        evidence=row["evidence"] + "; passive/unverified, weighting not calibrated",
    )


def _first(rows):
    return _detection(rows[0]) if rows else None


def detect_cms(html: str) -> TechDetection | None:
    return _first(_rows(html, category="cms"))


def detect_framework(html: str) -> TechDetection | None:
    rows = sorted(
        _rows(html, category="framework"), key=lambda row: (-row["confidence"], _priority(row))
    )
    return _first(rows)


def detect_analytics(html: str) -> list[TechDetection]:
    return [_detection(row) for row in _rows(html, category="analytics")]


def detect_server(headers: dict[str, str] | None = None) -> TechDetection | None:
    return _first(_rows(headers=headers, category="server"))


def detect_ecommerce(html: str) -> TechDetection | None:
    return _first(_rows(html, category="ecommerce"))


def detect_payment(html: str) -> list[TechDetection]:
    return [_detection(row) for row in _rows(html, category="payment")]


def detect_cdn(headers: dict[str, str] | None = None, html: str = "") -> TechDetection | None:
    return _first(_rows(html, headers, "cdn"))


def detect_language(headers: dict[str, str] | None = None, html: str = "") -> TechDetection | None:
    return _first(_rows(html, headers, "language"))


def fingerprint(html: str, headers: dict[str, str] | None = None) -> TechFingerprint:
    # One observation pass. The old schema has singleton slots; canonical evidence
    # keeps all matches, while this compatibility view selects deterministically.
    rows = observe_technologies(html, headers)
    grouped = {
        category: sorted([row for row in rows if row["category"] == category], key=_priority)
        for category in (
            "cms",
            "framework",
            "analytics",
            "server",
            "cdn",
            "ecommerce",
            "payment",
            "language",
        )
    }
    grouped["framework"].sort(key=lambda row: (-row["confidence"], _priority(row)))
    return TechFingerprint(
        cms=_first(grouped["cms"]),
        framework=_first(grouped["framework"]),
        analytics=[_detection(row) for row in grouped["analytics"]],
        server=_first(grouped["server"]),
        cdn=_first(grouped["cdn"]),
        ecommerce=_first(grouped["ecommerce"]),
        payment=[_detection(row) for row in grouped["payment"]],
        language=_first(grouped["language"]),
    )
