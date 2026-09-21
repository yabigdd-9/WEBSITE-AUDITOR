"""P12 deterministic NZD quote bands from versioned effort rules."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

QUOTE_RULES_VERSION = "quote-v1"
EFFORT_HOURS = {
    "XS": (Decimal("0.5"), Decimal("1.5")),
    "S": (Decimal("1.5"), Decimal("4")),
    "M": (Decimal("4"), Decimal("10")),
    "L": (Decimal("10"), Decimal("24")),
    "XL": (Decimal("24"), Decimal("60")),
}
PACKAGE_BANDS = (
    (Decimal("4"), "Quick Website Rescue"),
    (Decimal("12"), "Technical Repair"),
    (Decimal("30"), "Conversion Upgrade"),
    (Decimal("999999"), "Full Website Modernisation"),
)


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def calculate_quote(report: dict, hourly_rate_nzd, contingency=Decimal("0.15")) -> dict:
    try:
        rate = Decimal(str(hourly_rate_nzd))
        contingency = Decimal(str(contingency))
    except Exception as exc:
        raise ValueError("Numeric hourly_rate_nzd and contingency required") from exc
    if rate <= 0 or rate > Decimal("10000"):
        raise ValueError("hourly_rate_nzd outside allowed range")
    if contingency < 0 or contingency > Decimal("1"):
        raise ValueError("contingency must be between 0 and 1")
    defects = report.get("defects")
    if not isinstance(defects, list):
        raise ValueError("Audit report with defects required")

    grouped = {}
    for defect in defects:
        key = defect.get("defect_key")
        if not key:
            raise ValueError("Every defect needs defect_key")
        band = defect.get("effort_band") or "M"
        if band not in EFFORT_HOURS:
            raise ValueError(f"Unknown effort band: {band}")
        # Repeated occurrences of the same defect type do not multiply setup effort blindly.
        current = grouped.get(key)
        if current is None or EFFORT_HOURS[band][1] > EFFORT_HOURS[current["effort_band"]][1]:
            grouped[key] = {
                "defect_key": key,
                "defect": defect.get("defect", key),
                "effort_band": band,
                "finding_ids": [],
            }
        grouped[key]["finding_ids"].append(defect.get("finding_id"))

    low = sum((EFFORT_HOURS[x["effort_band"]][0] for x in grouped.values()), Decimal("0"))
    high = sum((EFFORT_HOURS[x["effort_band"]][1] for x in grouped.values()), Decimal("0"))
    high_with_contingency = high * (Decimal("1") + contingency)
    package = next(name for ceiling, name in PACKAGE_BANDS if high_with_contingency <= ceiling)
    confidence = (
        "HIGH" if report.get("status") == "complete" and all(d.get("confidence") != "heuristic" for d in defects)
        else "MEDIUM" if report.get("status") == "complete"
        else "LOW"
    )
    return {
        "schema_version": 1,
        "kind": "deterministic_quote",
        "rules_version": QUOTE_RULES_VERSION,
        "currency": "NZD",
        "source_run_id": report.get("run_id"),
        "package": package,
        "estimated_hours": {"low": _money(low), "high": _money(high_with_contingency)},
        "price_band_nzd": {
            "low": _money(low * rate),
            "high": _money(high_with_contingency * rate),
        },
        "hourly_rate_nzd": _money(rate),
        "contingency_fraction": str(contingency),
        "confidence": confidence,
        "included": [x["defect_key"] for x in grouped.values()],
        "excluded": [
            "Production deployment",
            "Paid third-party services",
            "Unverified scope outside audit evidence",
            "Client platform/licence fees",
        ],
        "assumptions": [
            "Effort bands come from versioned deterministic rules.",
            "Repeated instances of the same defect type share setup effort.",
            "Client access and hidden platform constraints may change scope.",
            "Price is an estimate until a human reviews scope and access.",
        ],
        "items": list(grouped.values()),
        "review_required": True,
        "llm_determined_price": False,
    }
