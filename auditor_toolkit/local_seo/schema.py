"""Canonical business entity, location, and evidence schemas.

All records preserve raw source values alongside normalized forms.
Evidence provenance tracks every claim back to its origin.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Consistency status
# ---------------------------------------------------------------------------

ConsistencyStatus = Literal[
    "MATCH",
    "EQUIVALENT_FORMAT",
    "PROBABLE_MATCH",
    "CONTRADICTION",
    "INSUFFICIENT_EVIDENCE",
    "NOT_APPLICABLE",
]

# ---------------------------------------------------------------------------
# Business type classification
# ---------------------------------------------------------------------------

BusinessLocationType = Literal[
    "PHYSICAL_LOCATION",
    "SERVICE_AREA",
    "HYBRID",
    "UNKNOWN",
]

# ---------------------------------------------------------------------------
# Geographic coordinates
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GeoCoordinates:
    latitude: float
    longitude: float

    def haversine_km(self, other: "GeoCoordinates") -> float:
        """Haversine distance in kilometres."""
        from math import asin, cos, radians, sin, sqrt

        earth_radius_km = 6371.0
        dlat = radians(other.latitude - self.latitude)
        dlon = radians(other.longitude - self.longitude)
        a = sin(dlat / 2) ** 2 + cos(radians(self.latitude)) * cos(
            radians(other.latitude)
        ) * sin(dlon / 2) ** 2
        return earth_radius_km * 2 * asin(sqrt(a))


# ---------------------------------------------------------------------------
# Normalized address
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NormalizedAddress:
    raw: str = ""
    street_number: str = ""
    street_name: str = ""
    unit: str = ""
    locality: str = ""
    region: str = ""
    postal_code: str = ""
    country: str = ""
    normalized: str = ""

    def signature(self) -> str:
        """Stable signature for deduplication (excludes unit)."""
        parts = [
            self.street_number,
            self.street_name,
            self.locality,
            self.region,
            self.postal_code,
            self.country,
        ]
        return "|".join(p.lower().strip() for p in parts if p)


# ---------------------------------------------------------------------------
# Normalized phone record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NormalizedPhone:
    raw: str = ""
    e164: str = ""
    region: str = ""
    possible: bool = False
    valid: bool = False
    phone_type: str = ""  # mobile, fixed_line, toll_free, etc.
    source: str = ""


# ---------------------------------------------------------------------------
# Normalized opening hour
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OpeningHour:
    day: str  # Monday, Tuesday, ...
    opens: str = ""  # HH:MM
    closes: str = ""  # HH:MM
    overnight: bool = False
    closed: bool = False
    special_text: str = ""  # "By appointment", "24 hours", etc.
    source: str = ""


# ---------------------------------------------------------------------------
# Business location entity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BusinessLocation:
    location_id: str
    business_id: str
    name: str = ""
    address: NormalizedAddress = field(default_factory=NormalizedAddress)
    phones: list[NormalizedPhone] = field(default_factory=list)
    geo: GeoCoordinates | None = None
    opening_hours: list[OpeningHour] = field(default_factory=list)
    page_urls: list[str] = field(default_factory=list)
    schema_entity_ids: list[str] = field(default_factory=list)
    location_type: BusinessLocationType = "UNKNOWN"
    confidence: float = 0.0
    evidence_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.geo:
            d["geo"] = {"latitude": self.geo.latitude, "longitude": self.geo.longitude}
        return d


# ---------------------------------------------------------------------------
# Named value with provenance
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NamedValue:
    value: str
    source: str
    confidence: float = 1.0


# ---------------------------------------------------------------------------
# Canonical business entity
# ---------------------------------------------------------------------------


@dataclass
class LocalBusinessEntity:
    business_id: str
    canonical_name: str = ""
    names: list[NamedValue] = field(default_factory=list)
    canonical_domain: str = ""
    domains: list[str] = field(default_factory=list)
    locations: list[BusinessLocation] = field(default_factory=list)
    phones: list[NormalizedPhone] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    service_areas: list[str] = field(default_factory=list)
    social_profiles: list[str] = field(default_factory=list)
    structured_data_entities: list[dict[str, Any]] = field(default_factory=list)
    parent_entity_id: str = ""
    branch_relationship: str = ""
    confidence: float = 0.0
    evidence_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# External local evidence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExternalLocalEvidence:
    provider: str
    retrieved_at: str
    query: str
    entity_identifier: str = ""
    name: str = ""
    address: str = ""
    phone: str = ""
    geo: GeoCoordinates | None = None
    categories: list[str] = field(default_factory=list)
    source_confidence: float = 0.0
    freshness: str = ""
    raw_artifact_hash: str = ""
    evidence_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.geo:
            d["geo"] = {"latitude": self.geo.latitude, "longitude": self.geo.longitude}
        return d
