"""Technology fingerprint detection — passive detection from HTML, headers, DOM."""

from __future__ import annotations

import re

from .schema import TechDetection, TechFingerprint

# ---------------------------------------------------------------------------
# CMS signatures
# ---------------------------------------------------------------------------

_CMS_PATTERNS: list[tuple[str, str, list[str]]] = [
    ("WordPress", "cms", [
        r'<meta\s+name="generator"\s+content="WordPress',
        r'/wp-includes/',
        r'/wp-content/',
        r'wpApiSettings',
        r'wp-json',
    ]),
    ("Shopify", "cms", [
        r'<meta\s+name="generator"\s+content="Shopify',
        r'cdn\.shopify\.com',
        r'Shopify\.shop\s*=',
        r'/cart/add',
    ]),
    ("Wix", "cms", [
        r'wix\.com',
        r'wixPublicUrl',
        r'static\.wixstatic\.com',
    ]),
    ("Squarespace", "cms", [
        r'squarespace\.com',
        r'squarespace\.universal',
    ]),
    ("Webflow", "cms", [
        r'webflow\.com',
        r'data-wf-site',
    ]),
]

# Framework signatures
_FRAMEWORK_PATTERNS: list[tuple[str, list[str]]] = [
    ("React", [r'react', r'rendered by React', r'data-reactroot']),
    ("Angular", [r'ng-app', r'ng-version', r'angular']),
    ("Vue", [r'vue', r'data-v-', r'__vue__']),
    ("jQuery", [r'jquery', r'jQuery', r'\$\.fn']),
    ("Bootstrap", [r'bootstrap', r'btn btn-', r'container-fluid']),
]

# Analytics signatures
_ANALYTICS_PATTERNS: list[tuple[str, list[str]]] = [
    ("Google Analytics", [r'google-analytics\.com/analytics\.js', r'gtag\(', r'ga\(']),
    ("Google Tag Manager", [r'googletagmanager\.com/gtm', r'dataLayer']),
    ("Hotjar", [r'hotjar\.com', r'hj\(']),
    ("Microsoft Clarity", [r'clarity\.microsoft\.com']),
    ("Facebook Pixel", [r'facebook\.com/tr', r'fbq\(']),
]

# Server signatures from headers
_SERVER_PATTERNS: dict[str, list[str]] = {
    "nginx": [r'nginx'],
    "Apache": [r'apache'],
    "IIS": [r'iis', r'microsoft-iis'],
    "Cloudflare": [r'cloudflare'],
    "LiteSpeed": [r'litespeed'],
}

# E-commerce signatures
_ECOMMERCE_PATTERNS: list[tuple[str, list[str]]] = [
    ("WooCommerce", [r'woocommerce', r'wc-ajax']),
    ("Magento", [r'magento', r'Mage\.']),
    ("BigCommerce", [r'bigcommerce']),
]

# Payment signatures
_PAYMENT_PATTERNS: list[tuple[str, list[str]]] = [
    ("Stripe", [r'stripe\.com', r'Stripe']),
    ("PayPal", [r'paypal\.com', r'paypal']),
    ("Square", [r'squareup\.com', r'Square']),
]

# CDN signatures from headers/URLs
_CDN_PATTERNS: list[tuple[str, list[str]]] = [
    ("Cloudflare", [r'cloudflare', r'cf-', r'cdn-cgi']),
    ("CloudFront", [r'cloudfront\.net']),
    ("Fastly", [r'fastly\.net']),
    ("Akamai", [r'akamai', r'edgekey']),
]

# Language detection
_LANGUAGE_PATTERNS: list[tuple[str, list[str]]] = [
    ("PHP", [r'<\?php', r'\.php[?"\']', r'X-Powered-By.*PHP']),
    ("Python", [r'X-Powered-By.*Python', r'WSGI']),
    ("Node.js", [r'X-Powered-By.*Express', r'Express']),
    ("Ruby", [r'X-Powered-By.*Ruby', r'Phusion.*Passenger']),
]


def _count_matches(html: str, patterns: list[str]) -> int:
    return sum(1 for p in patterns if re.search(p, html, re.IGNORECASE))


def _best_match(html: str, patterns: list[str]) -> tuple[str, float]:
    matches = _count_matches(html, patterns)
    if matches == 0:
        return "", 0.0
    return patterns[0].split("(")[0].split("[")[0].strip(), min(0.5 + matches * 0.15, 0.99)


def detect_cms(html: str) -> TechDetection | None:
    for name, _, patterns in _CMS_PATTERNS:
        matches = _count_matches(html, patterns)
        if matches > 0:
            evidence = [p for p in patterns if re.search(p, html, re.IGNORECASE)]
            confidence = min(0.6 + matches * 0.12, 0.99)
            return TechDetection(name=name, category="cms", confidence=confidence, evidence=", ".join(evidence[:2]))
    return None


def detect_framework(html: str) -> TechDetection | None:
    best_name, best_score = "", 0.0
    best_evidence = ""
    for name, patterns in _FRAMEWORK_PATTERNS:
        for p in patterns:
            if re.search(p, html, re.IGNORECASE):
                score = min(0.5 + _count_matches(html, patterns) * 0.15, 0.95)
                if score > best_score:
                    best_score = score
                    best_name = name
                    best_evidence = p
    if best_name:
        return TechDetection(name=best_name, category="framework", confidence=best_score, evidence=best_evidence)
    return None


def detect_analytics(html: str) -> list[TechDetection]:
    results = []
    for name, patterns in _ANALYTICS_PATTERNS:
        for p in patterns:
            if re.search(p, html, re.IGNORECASE):
                results.append(TechDetection(name=name, category="analytics", confidence=0.9, evidence=p))
                break
    return results


def detect_server(headers: dict[str, str] | None = None) -> TechDetection | None:
    if not headers:
        return None
    header_str = " ".join(f"{k}: {v}" for k, v in headers.items())
    for name, patterns in _SERVER_PATTERNS.items():
        for p in patterns:
            if re.search(p, header_str, re.IGNORECASE):
                return TechDetection(name=name, category="server", confidence=0.85, evidence=p)
    return None


def detect_ecommerce(html: str) -> TechDetection | None:
    for name, patterns in _ECOMMERCE_PATTERNS:
        if any(re.search(p, html, re.IGNORECASE) for p in patterns):
            return TechDetection(name=name, category="ecommerce", confidence=0.85)
    return None


def detect_payment(html: str) -> list[TechDetection]:
    results = []
    for name, patterns in _PAYMENT_PATTERNS:
        for p in patterns:
            if re.search(p, html, re.IGNORECASE):
                results.append(TechDetection(name=name, category="payment", confidence=0.85, evidence=p))
                break
    return results


def detect_cdn(headers: dict[str, str] | None = None, html: str = "") -> TechDetection | None:
    source = " ".join(f"{k}: {v}" for k, v in (headers or {}).items()) + " " + html
    for name, patterns in _CDN_PATTERNS:
        for p in patterns:
            if re.search(p, source, re.IGNORECASE):
                return TechDetection(name=name, category="cdn", confidence=0.85, evidence=p)
    return None


def detect_language(headers: dict[str, str] | None = None, html: str = "") -> TechDetection | None:
    source = " ".join(f"{k}: {v}" for k, v in (headers or {}).items()) + " " + html[:5000]
    for name, patterns in _LANGUAGE_PATTERNS:
        for p in patterns:
            if re.search(p, source, re.IGNORECASE):
                return TechDetection(name=name, category="language", confidence=0.8, evidence=p)
    return None


def fingerprint(html: str, headers: dict[str, str] | None = None) -> TechFingerprint:
    """Full technology fingerprint from HTML and response headers."""
    cms = detect_cms(html)
    framework = detect_framework(html)
    analytics = detect_analytics(html)
    server = detect_server(headers)
    cdn = detect_cdn(headers, html)
    ecommerce = detect_ecommerce(html)
    payment = detect_payment(html)
    language = detect_language(headers, html)

    from datetime import UTC, datetime
    return TechFingerprint(
        cms=cms,
        framework=framework,
        analytics=analytics,
        server=server,
        cdn=cdn,
        ecommerce=ecommerce,
        payment=payment,
        language=language,
    )
