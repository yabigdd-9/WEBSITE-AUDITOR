"""Audit profile resolution and deterministic site-type detection."""
from __future__ import annotations

import re
from typing import Any

PROFILES = {
    "quick": {"max_pages": 1, "browser": False, "accessibility": False, "performance": False},
    "standard": {"max_pages": 5, "browser": False, "accessibility": False, "performance": False},
    "deep": {"max_pages": 25, "browser": True, "accessibility": True, "performance": True},
    "ecommerce": {"max_pages": 15, "browser": True, "accessibility": True, "performance": True},
    "leadgen": {"max_pages": 10, "browser": True, "accessibility": True, "performance": True},
    "nz_small_business": {"max_pages": 10, "browser": False, "accessibility": True, "performance": False},
}


def detect_site_type(html: str, schema_types: list[str] | None = None) -> dict[str, Any]:
    text = (html or "").lower()
    schema = {str(item).lower() for item in (schema_types or [])}

    signals: list[str] = []
    site_type = "brochure"

    ecommerce_hits = [
        r"add[-_ ]to[-_ ]cart",
        r"cart",
        r"checkout",
        r"product",
        r"shopify",
        r"woocommerce",
    ]
    booking_hits = [r"book now", r"booking", r"calendly", r"appointment"]
    lead_hits = [r"request (a )?quote", r"get (a )?quote", r"contact us", r"enquire", r"enquiry"]

    if schema.intersection({"product", "offer"}) or any(re.search(p, text) for p in ecommerce_hits):
        site_type = "ecommerce"
        signals.append("commerce/cart/product signal")
    elif any(re.search(p, text) for p in booking_hits):
        site_type = "booking_service"
        signals.append("booking/appointment signal")
    elif "<form" in text or any(re.search(p, text) for p in lead_hits):
        site_type = "lead_generation"
        signals.append("form/quote/contact signal")
    elif "application/ld+json" in text and schema.intersection({"article", "blogposting", "newsarticle"}):
        site_type = "content"
        signals.append("article schema signal")
    elif re.search(r"__next|/_next/", text):
        site_type = "single_page_or_hybrid_app"
        signals.append("Next.js signal")

    return {"site_type": site_type, "signals": signals}


def resolve_profile(requested: str, detected_site_type: str) -> tuple[str, dict[str, Any]]:
    if requested != "auto":
        name = requested
    elif detected_site_type == "ecommerce":
        name = "ecommerce"
    elif detected_site_type in {"booking_service", "lead_generation"}:
        name = "leadgen"
    else:
        name = "nz_small_business"
    return name, dict(PROFILES[name])
