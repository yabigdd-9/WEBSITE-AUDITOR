"""Canonical passive technology evidence and compatibility records."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .technology.observations import METHOD, observe_technologies


@dataclass
class Technology:
    technology: str
    category: str
    version: str | None = None
    version_confidence: float = 0.0
    evidence: str = ""
    confidence: float = 0.0
    confidence_calibrated: bool = False
    confidence_basis: str = "preserved signature weighting; not a probability"
    version_status: str = "unknown_or_ambiguous"
    evidence_sources: list[dict[str, str]] = field(default_factory=list)


def detect_technology(html: str, url: str, headers: dict) -> list[Technology]:
    rows = observe_technologies(html, headers, url)
    categories = {
        "cms": "CMS",
        "framework": "JavaScript Framework",
        "analytics": "Analytics",
        "ecommerce": "Ecommerce",
        "server": "Server",
        "cdn": "CDN",
        "language": "Programming Language",
        "runtime": "Runtime",
        "payment": "Payment",
        "page_builder": "Page Builder",
        "caching": "Caching",
    }
    result = []
    for row in rows:
        category = categories.get(row["category"], row["category"])
        if row["name"] == "Bootstrap":
            category = "CSS Framework"
        elif row["name"] == "jQuery":
            category = "JavaScript Library"
        result.append(
            Technology(
                row["name"],
                category,
                row["version"],
                row["version_confidence"],
                row["evidence"],
                row["confidence"],
                row["confidence_calibrated"],
                row["confidence_basis"],
                row["version_status"],
                row["signals"],
            )
        )
    # Keep CMS records first for established canonical report consumers.
    return sorted(
        result, key=lambda row: (row.category != "CMS", row.category, row.technology.casefold())
    )


def analyse_html(html: str, url: str, headers: dict) -> tuple[list[Any], dict[str, Any]]:
    """Technology clues are evidence only; they do not produce defect deductions."""
    return [], {
        "method": METHOD,
        "technologies": [asdict(row) for row in detect_technology(html, url, headers)],
        "installation_confirmed": False,
        "vulnerability_assessed": False,
        "limitation": "Passive signature clues and declared version tokens; no active verification or calibrated confidence.",
    }
