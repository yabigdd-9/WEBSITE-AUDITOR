"""Conservative ecommerce-specific passive checks."""
from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any

import bs4


ECOMMERCE_HINTS = re.compile(
    r"\b(add to cart|cart|checkout|buy now|shopify|woocommerce|product)\b",
    re.IGNORECASE,
)
SHIPPING_TERMS = re.compile(r"\b(shipping|delivery|freight)\b", re.IGNORECASE)
RETURNS_TERMS = re.compile(r"\b(return|returns|refund|exchange)\b", re.IGNORECASE)
GST_TERMS = re.compile(r"\b(gst|goods and services tax|incl\.? gst|includes gst|excluding gst|excl\.? gst)\b", re.IGNORECASE)
TRUST_TERMS = re.compile(
    r"\b(secure checkout|secure payment|ssl secure|money[- ]back|buyer protection)\b",
    re.IGNORECASE,
)


def _schema_types(soup: bs4.BeautifulSoup) -> set[str]:
    types: set[str] = set()
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        def collect(value: Any) -> None:
            if isinstance(value, dict):
                item_type = value.get("@type")
                if isinstance(item_type, str):
                    types.add(item_type.lower())
                elif isinstance(item_type, list):
                    types.update(str(item).lower() for item in item_type)
                for nested in value.values():
                    collect(nested)
            elif isinstance(value, list):
                for nested in value:
                    collect(nested)

        collect(data)
    return types


def ecommerce_checks(
    html: str,
    *,
    base_url: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    soup = bs4.BeautifulSoup(html or "", "lxml")
    text = soup.get_text(" ", strip=True)
    markup = html or ""
    schema = _schema_types(soup)

    ecommerce_signal = bool(
        ECOMMERCE_HINTS.search(f"{text} {markup}")
        or schema.intersection({"product", "offer", "aggregateoffer"})
    )
    if not ecommerce_signal:
        return [], {"ecommerce_detected": False}

    defects: list[dict[str, Any]] = []
    if not schema.intersection({"product", "offer", "aggregateoffer"}):
        defects.append(
            {
                "defect": "Ecommerce product schema not detected",
                "impact": "Product rich-result eligibility may be limited",
            }
        )

    shipping = bool(SHIPPING_TERMS.search(text))
    returns = bool(RETURNS_TERMS.search(text))
    gst = bool(GST_TERMS.search(text))
    trust = bool(TRUST_TERMS.search(text))

    if not shipping or not returns:
        defects.append(
            {
                "defect": "Shipping or returns information not clearly detected",
                "impact": "Purchase confidence may be reduced; manual review is recommended",
            }
        )

    if not gst:
        defects.append(
            {
                "defect": "GST pricing clarity not detected",
                "impact": "NZ customers may need clearer tax-inclusive/exclusive price context",
            }
        )

    insecure_checkout_urls: list[str] = []
    for node in soup.find_all(["a", "form"]):
        raw = node.get("href") if node.name == "a" else node.get("action")
        if not raw:
            continue
        visible = node.get_text(" ", strip=True).lower()
        classes = " ".join(node.get("class", []))
        marker = f"{visible} {classes} {raw}".lower()
        if "checkout" not in marker and "cart" not in marker and "payment" not in marker:
            continue
        absolute = urllib.parse.urljoin(base_url, str(raw))
        parsed = urllib.parse.urlsplit(absolute)
        if parsed.scheme == "http":
            insecure_checkout_urls.append(absolute)

    if insecure_checkout_urls:
        defects.append(
            {
                "defect": f"{len(insecure_checkout_urls)} insecure checkout/payment URL(s) detected",
                "impact": "Checkout or payment navigation over HTTP can expose sensitive traffic",
            }
        )

    review_nodes = soup.select(
        '[itemprop="review"], [itemprop="aggregateRating"], .review, .reviews, [class*="rating"]'
    )
    evidence = {
        "ecommerce_detected": True,
        "schema_types": sorted(schema),
        "product_schema_present": bool(schema.intersection({"product", "offer", "aggregateoffer"})),
        "shipping_signal": shipping,
        "returns_signal": returns,
        "gst_signal": gst,
        "trust_signal": trust,
        "review_signal_count": len(review_nodes),
        "review_note": (
            "Review presence is reported as a signal only. Passive HTML cannot prove review authenticity."
        ),
        "insecure_checkout_urls": insecure_checkout_urls,
    }
    return defects, evidence
