"""Service-area classification.

Classifies a business as PHYSICAL_LOCATION, SERVICE_AREA, HYBRID, or UNKNOWN.
Service-area businesses legitimately hide their address — this must NOT be
auto-flagged as a defect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .schema import BusinessLocationType

ServiceAreaClassification = Literal[
    "PHYSICAL_LOCATION",
    "SERVICE_AREA",
    "HYBRID",
    "UNKNOWN",
]


@dataclass(frozen=True)
class ServiceAreaAnalysis:
    """Result of service-area classification."""

    classification: ServiceAreaClassification
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)
    has_physical_address: bool = False
    has_service_area_list: bool = False
    address_hidden: bool = False
    schema_type: str = ""
    page_signals: dict[str, Any] = field(default_factory=dict)

    @property
    def is_service_area(self) -> bool:
        return self.classification == "SERVICE_AREA"

    @property
    def is_physical(self) -> bool:
        return self.classification == "PHYSICAL_LOCATION"

    @property
    def requires_address(self) -> bool:
        return not self.has_physical_address and self.classification != "SERVICE_AREA"

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "confidence": self.confidence,
            "reasons": self.reasons,
            "has_physical_address": self.has_physical_address,
            "has_service_area_list": self.has_service_area_list,
            "address_hidden": self.address_hidden,
            "schema_type": self.schema_type,
            "page_signals": self.page_signals,
        }


# ---------------------------------------------------------------------------
# Signals that indicate service-area vs physical
# ---------------------------------------------------------------------------

_SERVICE_AREA_KEYWORDS = frozenset(
    {
        "we come to you",
        "mobile service",
        "service area",
        "we serve",
        "covering",
        "areas we cover",
        "serving",
        "delivery area",
        "mobile",
        "on-site",
        "at your location",
        "we travel to you",
        "call-out",
        "home visit",
    }
)

_PHYSICAL_KEYWORDS = frozenset(
    {
        "visit us",
        "our office",
        "our store",
        "come in",
        "open hours",
        "opening hours",
        "walk in",
        "showroom",
        "reception",
        "appointment at our office",
    }
)


# ---------------------------------------------------------------------------
# Classification logic
# ---------------------------------------------------------------------------


def classify_service_area(
    has_address: bool = False,
    address_visible: bool = True,
    service_areas: list[str] | None = None,
    page_text: str = "",
    schema_type: str = "",
    schema_has_address: bool = False,
    schema_has_service_area: bool = False,
) -> ServiceAreaAnalysis:
    """Classify business type from available signals.

    A SERVICE_AREA business has no physical address that customers visit.
    A PHYSICAL_LOCATION business has a customer-accessible address.
    A HYBRID business has both a physical location and service areas.
    """
    sa_list = service_areas or []
    has_sa_list = len(sa_list) > 0
    classification, score, reasons = _schema_classification(
        has_address,
        address_visible,
        has_sa_list,
        schema_has_address,
        schema_has_service_area,
    )

    # Page content signals
    page_lower = page_text.lower()
    sa_keywords_found = [kw for kw in _SERVICE_AREA_KEYWORDS if kw in page_lower]
    physical_keywords_found = [kw for kw in _PHYSICAL_KEYWORDS if kw in page_lower]

    classification, score = _apply_service_area_keywords(
        classification, score, reasons, sa_keywords_found, physical_keywords_found
    )
    classification, score = _apply_physical_keywords(
        classification, score, reasons, sa_keywords_found, physical_keywords_found
    )

    # Service area list without address → SERVICE_AREA
    if has_sa_list and not has_address and classification == "UNKNOWN":
        classification = "SERVICE_AREA"
        score = 0.75
        reasons.append(f"Service areas listed ({len(sa_list)} areas), no address")

    # No strong signals → UNKNOWN
    if classification == "UNKNOWN":
        score = 0.0
        reasons.append("Insufficient signals to classify")

    return ServiceAreaAnalysis(
        classification=classification,
        confidence=round(score, 2),
        reasons=reasons,
        has_physical_address=has_address and address_visible,
        has_service_area_list=has_sa_list,
        address_hidden=has_address and not address_visible,
        schema_type=schema_type,
        page_signals={
            "service_area_keywords": sa_keywords_found,
            "physical_keywords": physical_keywords_found,
        },
    )


def _schema_classification(
    has_address: bool,
    address_visible: bool,
    has_service_area_list: bool,
    schema_has_address: bool,
    schema_has_service_area: bool,
) -> tuple[ServiceAreaClassification, float, list[str]]:
    reasons: list[str] = []
    if schema_has_service_area and (schema_has_address or (has_address and address_visible)):
        return "HYBRID", 0.8, ["Service area plus a visible/schema physical address"]
    if schema_has_service_area:
        return "SERVICE_AREA", 0.85, ["Schema: serviceArea present, no physical address"]
    if schema_has_address and not has_service_area_list and has_address:
        score = 0.7 if address_visible else 0.45
        reason = (
            "Schema address present and visible on page"
            if address_visible
            else "Schema address present but not visible on page"
        )
        return "PHYSICAL_LOCATION", score, [reason]
    return "UNKNOWN", 0.0, reasons


def _apply_service_area_keywords(classification, score, reasons, service_keywords, physical_keywords):
    if not service_keywords:
        return classification, score
    reasons.append(f"Page content indicates service area: {', '.join(service_keywords[:3])}")
    if classification == "PHYSICAL_LOCATION" and physical_keywords:
        return "HYBRID", max(score, 0.5)
    if classification == "UNKNOWN" or classification == "PHYSICAL_LOCATION":
        return "SERVICE_AREA", max(score, 0.6)
    if classification == "SERVICE_AREA":
        return classification, min(score + 0.1, 1.0)
    return classification, score


def _apply_physical_keywords(classification, score, reasons, service_keywords, physical_keywords):
    if not physical_keywords:
        return classification, score
    reasons.append(f"Page content indicates physical location: {', '.join(physical_keywords[:3])}")
    if classification == "SERVICE_AREA" and not service_keywords:
        return "PHYSICAL_LOCATION", max(score, 0.55)
    if classification == "SERVICE_AREA":
        return "HYBRID", max(score, 0.5)
    if classification == "UNKNOWN":
        return "PHYSICAL_LOCATION", max(score, 0.4)
    return classification, score


def should_flag_missing_address(
    analysis: ServiceAreaAnalysis | None = None,
    *,
    has_address: bool | None = None,
    has_area_served: bool = False,
) -> bool:
    """Return whether a missing physical address is a defensible defect.

    The canonical API accepts a ServiceAreaAnalysis object. Legacy boolean
    arguments remain supported while preserving the fail-closed rule:
    service-area evidence suppresses a missing-address defect.
    """
    if analysis is None:
        analysis = classify_service_area(
            has_address=bool(has_address),
            service_areas=["region"] if has_area_served else None,
        )

    if analysis.classification == "SERVICE_AREA":
        return False
    if analysis.classification == "UNKNOWN" and analysis.confidence < 0.3:
        return False
    return not analysis.has_physical_address


def to_location_type(analysis: ServiceAreaAnalysis) -> BusinessLocationType:
    """Map ServiceAreaClassification to BusinessLocationType."""
    return analysis.classification  # Same Literal values


# ---------------------------------------------------------------------------
# Compatibility aliases for pre-integration test API
# ---------------------------------------------------------------------------

def classify_business_type(
    has_address: bool = False,
    has_service_area_schema: bool = False,
    areas_served: list[str] | None = None,
) -> "ServiceAreaAnalysis":
    """Compatibility wrapper matching v38 test expectations."""
    return classify_service_area(
        has_address=has_address,
        schema_has_service_area=has_service_area_schema,
        service_areas=areas_served,
    )

